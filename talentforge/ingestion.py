"""Secure telemetry ingestion and live agent streaming routes for TalentForge."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
    status,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from talentforge.auth import get_user_from_access_token
from talentforge.db.database import get_db_session
from talentforge.db.models import (
    AgentAuditLog,
    InteractionHistory,
    TelemetryIngestionDeduplication,
    User,
    UserRole,
)


logger = logging.getLogger("talentforge.ingestion")

WEBHOOK_SECRET_ENV = "WEBHOOK_SECRET_TOKEN"
WEBHOOK_SIGNATURE_HEADER = "X-TalentForge-Signature"
MIN_WEBHOOK_SECRET_BYTES = 32
SUPPORTED_SIGNATURE_PREFIX = "sha256="

router = APIRouter(tags=["telemetry"])


class TelemetryEventIn(BaseModel):
    """Validated ingestion envelope for platform metrics and error logs."""

    model_config = ConfigDict(extra="allow")

    customer_id: UUID
    event_type: str = Field(min_length=1, max_length=100)
    error_signature: str | None = Field(default=None, min_length=1, max_length=512)
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None


class TelemetryEventAccepted(BaseModel):
    accepted: bool
    event_id: UUID
    idempotency_key: str
    hour_bucket: datetime


class AgentStreamManager:
    """Track WebSocket clients by agent session and fan out JSON updates."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[session_id].add(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        connections = self._connections.get(session_id)
        if connections is None:
            return
        connections.discard(websocket)
        if not connections:
            self._connections.pop(session_id, None)

    async def send_json(
        self,
        session_id: str,
        payload: dict[str, Any],
    ) -> None:
        stale_connections: list[WebSocket] = []
        for websocket in tuple(self._connections.get(session_id, ())):
            try:
                await websocket.send_json(payload)
            except RuntimeError:
                stale_connections.append(websocket)

        for websocket in stale_connections:
            self.disconnect(session_id, websocket)

    async def broadcast_agent_update(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        await self.send_json(
            session_id,
            {
                "type": event_type,
                "session_id": session_id,
                "payload": payload,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )


agent_stream_manager = AgentStreamManager()


def _log_ingestion_security_event(event: str, **fields: object) -> None:
    details = " ".join(f"{key}={value}" for key, value in sorted(fields.items()))
    logger.warning("ingestion_security_event=%s %s", event, details)


def _load_webhook_secret() -> bytes:
    secret = os.getenv(WEBHOOK_SECRET_ENV, "")
    if len(secret.encode("utf-8")) < MIN_WEBHOOK_SECRET_BYTES:
        logger.critical("webhook_security_configuration_rejected reason=missing_or_short_secret")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook security is not configured.",
        )
    return secret.encode("utf-8")


def _normalize_signature(signature: str | None) -> str | None:
    if signature is None:
        return None
    value = signature.strip()
    if value.startswith(SUPPORTED_SIGNATURE_PREFIX):
        value = value.removeprefix(SUPPORTED_SIGNATURE_PREFIX)
    return value.lower()


def _verify_webhook_signature(raw_body: bytes, signature: str | None) -> None:
    supplied_signature = _normalize_signature(signature)
    if not supplied_signature:
        _log_ingestion_security_event("missing_webhook_signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing webhook signature.",
        )

    expected_signature = hmac.new(
        _load_webhook_secret(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        _log_ingestion_security_event("invalid_webhook_signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature.",
        )


def _utc_hour_bucket(now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    return current.astimezone(timezone.utc).replace(
        minute=0,
        second=0,
        microsecond=0,
    )


def _resolve_error_signature(event: TelemetryEventIn, raw_body: bytes) -> str:
    if event.error_signature:
        return event.error_signature.strip()
    payload_hash = hashlib.sha256(raw_body).hexdigest()
    return f"{event.event_type}:{payload_hash}"


def build_idempotency_key(
    customer_id: UUID,
    error_signature: str,
    hour_bucket: datetime,
) -> str:
    key_material = f"{customer_id}{error_signature}{hour_bucket.isoformat()}"
    return hashlib.md5(key_material.encode("utf-8"), usedforsecurity=False).hexdigest()


async def _reserve_idempotency_key(
    session: AsyncSession,
    *,
    idempotency_key: str,
    customer_id: UUID,
    error_signature: str,
    hour_bucket: datetime,
) -> bool:
    statement = (
        insert(TelemetryIngestionDeduplication)
        .values(
            idempotency_key=idempotency_key,
            customer_id=customer_id,
            error_signature=error_signature,
            hour_bucket=hour_bucket,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(TelemetryIngestionDeduplication.id)
    )
    result = await session.execute(statement)
    return result.scalar_one_or_none() is not None


async def get_websocket_current_user(
    websocket: WebSocket,
    access_token: Annotated[str | None, Query(alias="access_token")] = None,
    session: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> User:
    authorization_header = websocket.headers.get("authorization", "")
    bearer_prefix = "bearer "
    token = access_token
    if authorization_header.lower().startswith(bearer_prefix):
        token = authorization_header[len(bearer_prefix) :].strip()

    if not token:
        _log_ingestion_security_event("missing_websocket_token")
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    try:
        return await get_user_from_access_token(
            session,
            token,
            required_roles=[
                UserRole.ADMIN.value,
                UserRole.CSM.value,
                UserRole.VIEWER.value,
            ],
        )
    except HTTPException:
        _log_ingestion_security_event("invalid_websocket_token")
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)


@router.post(
    "/api/telemetry/event",
    response_model=TelemetryEventAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_telemetry_event(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    signature: Annotated[str | None, Header(alias=WEBHOOK_SIGNATURE_HEADER)] = None,
) -> TelemetryEventAccepted:
    raw_body = await request.body()
    _verify_webhook_signature(raw_body, signature)

    try:
        event = TelemetryEventIn.model_validate_json(raw_body)
    except ValidationError as exc:
        _log_ingestion_security_event("invalid_telemetry_payload")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc

    hour_bucket = _utc_hour_bucket()
    error_signature = _resolve_error_signature(event, raw_body)
    idempotency_key = build_idempotency_key(
        event.customer_id,
        error_signature,
        hour_bucket,
    )

    reserved = await _reserve_idempotency_key(
        session,
        idempotency_key=idempotency_key,
        customer_id=event.customer_id,
        error_signature=error_signature,
        hour_bucket=hour_bucket,
    )
    if not reserved:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Duplicate telemetry event rejected for this hour window.",
                "idempotency_key": idempotency_key,
            },
        )

    interaction = InteractionHistory(
        customer_id=event.customer_id,
        event_type=event.event_type,
        raw_payload=raw_body.decode("utf-8", errors="replace"),
        timestamp=event.occurred_at or datetime.now(timezone.utc),
    )
    audit_log = AgentAuditLog(
        session_id=idempotency_key,
        node_name="telemetry_ingestion",
        action_taken="accepted telemetry event",
        metadata_json={
            "customer_id": str(event.customer_id),
            "event_type": event.event_type,
            "idempotency_key": idempotency_key,
            "hour_bucket": hour_bucket.isoformat(),
        },
    )
    session.add(interaction)
    session.add(audit_log)
    await session.commit()
    await session.refresh(interaction)

    await agent_stream_manager.broadcast_agent_update(
        str(event.customer_id),
        "telemetry_event_accepted",
        {
            "event_id": str(interaction.id),
            "event_type": event.event_type,
            "idempotency_key": idempotency_key,
        },
    )

    return TelemetryEventAccepted(
        accepted=True,
        event_id=interaction.id,
        idempotency_key=idempotency_key,
        hour_bucket=hour_bucket,
    )


@router.websocket("/ws/agent/stream/{session_id}")
async def agent_stream_websocket(
    websocket: WebSocket,
    session_id: str,
    current_user: Annotated[User, Depends(get_websocket_current_user)],
) -> None:
    await agent_stream_manager.connect(session_id, websocket)
    await websocket.send_json(
        {
            "type": "agent_stream_connected",
            "session_id": session_id,
            "user_id": str(current_user.id),
            "role": current_user.role.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )

    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "ping":
                await websocket.send_json(
                    {
                        "type": "pong",
                        "session_id": session_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
    except WebSocketDisconnect:
        agent_stream_manager.disconnect(session_id, websocket)
    except Exception:
        agent_stream_manager.disconnect(session_id, websocket)
        logger.exception("agent_stream_websocket_failed session_id=%s", session_id)
        raise
