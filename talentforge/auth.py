"""Password authentication and JWT-backed role enforcement for TalentForge."""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Final
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, ExpiredSignatureError, jwt
from passlib.context import CryptContext
from passlib.exc import UnknownHashError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from talentforge.db.database import get_db_session
from talentforge.db.models import User, UserRole


logger = logging.getLogger("talentforge.security")

JWT_SECRET_KEY_ENV: Final = "JWT_SECRET_KEY"
JWT_ISSUER_ENV: Final = "JWT_ISSUER"
JWT_AUDIENCE_ENV: Final = "JWT_AUDIENCE"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES_ENV: Final = "JWT_ACCESS_TOKEN_EXPIRE_MINUTES"

JWT_ALGORITHM: Final = "HS256"
JWT_ISSUER: Final = "talentforge-api"
JWT_AUDIENCE: Final = "talentforge-api"
DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES: Final = 15
MAX_ACCESS_TOKEN_EXPIRE_MINUTES: Final = 60
MIN_JWT_SECRET_BYTES: Final = 32
MIN_PASSWORD_LENGTH: Final = 12
MAX_BCRYPT_PASSWORD_BYTES: Final = 72

password_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
    bcrypt__truncate_error=True,
)
bearer_scheme = HTTPBearer(bearerFormat="JWT", auto_error=False)


@dataclass(frozen=True, slots=True)
class JWTSettings:
    """Validated runtime JWT configuration; the secret is never logged."""

    secret_key: str
    issuer: str
    audience: str
    access_token_expire_minutes: int


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    """Claims accepted after signature and semantic validation."""

    subject: UUID
    role: UserRole


def _log_security_event(level: int, event: str, **fields: object) -> None:
    """Send security-relevant events to the application's configured log handlers."""
    details = " ".join(f"{key}={value}" for key, value in sorted(fields.items()))
    logger.log(level, "security_event=%s %s", event, details)


def _reject_jwt_configuration(reason: str) -> None:
    _log_security_event(logging.CRITICAL, "jwt_configuration_rejected", reason=reason)
    raise RuntimeError("JWT security configuration is invalid.")


def _read_access_token_lifetime() -> int:
    raw_value = os.getenv(
        JWT_ACCESS_TOKEN_EXPIRE_MINUTES_ENV,
        str(DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    try:
        lifetime = int(raw_value)
    except ValueError:
        _reject_jwt_configuration("invalid_access_token_lifetime")

    if not 1 <= lifetime <= MAX_ACCESS_TOKEN_EXPIRE_MINUTES:
        _reject_jwt_configuration("access_token_lifetime_out_of_range")
    return lifetime


def _load_jwt_settings() -> JWTSettings:
    """Load and validate security settings at token-use time, never at import time."""
    secret_key = os.getenv(JWT_SECRET_KEY_ENV, "")
    if len(secret_key.encode("utf-8")) < MIN_JWT_SECRET_BYTES:
        _reject_jwt_configuration("missing_or_short_jwt_secret")

    issuer = os.getenv(JWT_ISSUER_ENV, JWT_ISSUER).strip()
    audience = os.getenv(JWT_AUDIENCE_ENV, JWT_AUDIENCE).strip()
    if not issuer or not audience:
        _reject_jwt_configuration("empty_jwt_issuer_or_audience")

    return JWTSettings(
        secret_key=secret_key,
        issuer=issuer,
        audience=audience,
        access_token_expire_minutes=_read_access_token_lifetime(),
    )


def _validate_password(plain_password: str) -> None:
    if len(plain_password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"Passwords must contain at least {MIN_PASSWORD_LENGTH} characters."
        )
    if len(plain_password.encode("utf-8")) > MAX_BCRYPT_PASSWORD_BYTES:
        raise ValueError(
            "Passwords cannot exceed 72 UTF-8 bytes when using bcrypt."
        )


def hash_password(plain_password: str) -> str:
    """Hash a new password with bcrypt at the configured work factor."""
    _validate_password(plain_password)
    return password_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a bcrypt password hash without exposing verification details."""
    try:
        return password_context.verify(plain_password, hashed_password)
    except (UnknownHashError, ValueError):
        _log_security_event(logging.ERROR, "invalid_stored_password_hash")
        return False


async def authenticate_user(
    session: AsyncSession,
    email: str,
    password: str,
) -> User | None:
    """Authenticate a user while minimizing account-enumeration timing signals."""
    normalized_email = email.strip().lower()
    result = await session.execute(select(User).where(User.email == normalized_email))
    user = result.scalar_one_or_none()

    if user is None:
        # Preserve bcrypt work for non-existent accounts without logging PII.
        password_context.hash("talentforge-timing-equalization")
        _log_security_event(logging.WARNING, "authentication_failed")
        return None

    if not verify_password(password, user.hashed_password):
        _log_security_event(logging.WARNING, "authentication_failed")
        return None
    return user


def _role_from_value(role: object, *, source: str) -> UserRole:
    if not isinstance(role, str):
        _log_security_event(logging.WARNING, "invalid_role_claim", source=source)
        raise ValueError("Role must be a string.")
    try:
        return UserRole(role)
    except ValueError:
        _log_security_event(logging.WARNING, "invalid_role_claim", source=source)
        raise


def _normalize_required_roles(required_roles: list[str] | None) -> frozenset[UserRole]:
    if not required_roles:
        return frozenset()

    try:
        return frozenset(_role_from_value(role, source="endpoint_configuration") for role in required_roles)
    except ValueError as exc:
        _log_security_event(logging.CRITICAL, "rbac_configuration_rejected")
        raise RuntimeError("Endpoint declares an invalid required role.") from exc


def create_access_token(user: User) -> str:
    """Issue a short-lived, signed access token for an authenticated user."""
    settings = _load_jwt_settings()
    try:
        role = UserRole(user.role)
    except ValueError as exc:
        _log_security_event(logging.CRITICAL, "user_has_invalid_database_role")
        raise RuntimeError("User has an invalid role assignment.") from exc

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {
            "sub": str(user.id),
            "role": role.value,
            "scope": f"role:{role.value}",
            "type": "access",
            "iss": settings.issuer,
            "aud": settings.audience,
            "iat": now,
            "nbf": now,
            "exp": expires_at,
            "jti": str(uuid4()),
        },
        settings.secret_key,
        algorithm=JWT_ALGORITHM,
    )


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _decode_access_token(token: str) -> AccessTokenClaims:
    settings = _load_jwt_settings()
    try:
        claims = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[JWT_ALGORITHM],
            audience=settings.audience,
            issuer=settings.issuer,
            options={
                "require_exp": True,
                "require_iat": True,
                "require_nbf": True,
                "require_sub": True,
                "require_jti": True,
            },
        )
    except ExpiredSignatureError:
        _log_security_event(logging.WARNING, "expired_access_token")
        raise _credentials_exception()
    except JWTError:
        _log_security_event(logging.WARNING, "invalid_access_token")
        raise _credentials_exception()

    if claims.get("type") != "access":
        _log_security_event(logging.WARNING, "invalid_token_type")
        raise _credentials_exception()

    try:
        subject = UUID(str(claims["sub"]))
        role = _role_from_value(claims.get("role"), source="access_token")
    except (KeyError, ValueError, TypeError):
        _log_security_event(logging.WARNING, "invalid_access_token_identity")
        raise _credentials_exception()

    scopes = claims.get("scope")
    expected_scope = f"role:{role.value}"
    if not isinstance(scopes, str) or set(scopes.split()) != {expected_scope}:
        _log_security_event(logging.WARNING, "invalid_token_scope")
        raise _credentials_exception()

    return AccessTokenClaims(subject=subject, role=role)


async def _resolve_authenticated_user(
    session: AsyncSession,
    token: str,
    allowed_roles: frozenset[UserRole],
) -> User:
    token_claims = _decode_access_token(token)
    user = await session.get(User, token_claims.subject)
    if user is None:
        _log_security_event(logging.WARNING, "token_subject_not_found")
        raise _credentials_exception()

    if user.role != token_claims.role:
        _log_security_event(logging.WARNING, "token_role_mismatch")
        raise _credentials_exception()

    if allowed_roles and user.role not in allowed_roles:
        _log_security_event(logging.WARNING, "rbac_access_denied")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions.",
        )
    return user


async def get_user_from_access_token(
    session: AsyncSession,
    token: str,
    required_roles: list[str] | None = None,
) -> User:
    """Validate a JWT and return the matching database user for non-HTTP flows."""
    return await _resolve_authenticated_user(
        session,
        token,
        _normalize_required_roles(required_roles),
    )


def get_current_active_user(
    required_roles: list[str] | None = None,
) -> Callable[..., Awaitable[User]]:
    """
    Build a FastAPI dependency that validates the Bearer token and enforces RBAC.

    Use ``Depends(get_current_active_user())`` for authentication or pass endpoint
    roles explicitly, such as ``Depends(get_current_active_user(["admin", "csm"]))``.
    """
    allowed_roles = _normalize_required_roles(required_roles)

    async def current_active_user_dependency(
        credentials: Annotated[
            HTTPAuthorizationCredentials | None,
            Depends(bearer_scheme),
        ],
        session: Annotated[AsyncSession, Depends(get_db_session)],
    ) -> User:
        if credentials is None or credentials.scheme.lower() != "bearer":
            _log_security_event(logging.WARNING, "missing_or_invalid_bearer_header")
            raise _credentials_exception()

        return await _resolve_authenticated_user(
            session,
            credentials.credentials,
            allowed_roles,
        )

    return current_active_user_dependency
