"""Asynchronous PostgreSQL orchestration for TalentForge."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv

load_dotenv()  # Load .env file so DATABASE_URL and other vars are available

from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel import SQLModel

import talentforge.db.models  # noqa: F401  Import registers SQLModel metadata.


DATABASE_URL_ENV = "DATABASE_URL"
DEFAULT_STATEMENT_TIMEOUT_MS = 30_000

PGVECTOR_EXTENSION_SQL = "CREATE EXTENSION IF NOT EXISTS vector;"
PGVECTOR_EXTENSION_REQUESTED_FALLBACK_SQL = "CREATE EXTENSION IF NOT EXISTS pgvector;"
PGVECTOR_EXTENSION_SQL_CANDIDATES: tuple[str, ...] = (
    PGVECTOR_EXTENSION_SQL,
    PGVECTOR_EXTENSION_REQUESTED_FALLBACK_SQL,
)

APP_READONLY_ROLE_SQL: tuple[str, ...] = (
    """
    DO $$
    BEGIN
        CREATE ROLE app_readonly NOLOGIN;
    EXCEPTION
        WHEN duplicate_object THEN NULL;
    END
    $$;
    """,
    "GRANT USAGE ON SCHEMA public TO app_readonly;",
    "GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_readonly;",
    "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO app_readonly;",
    "ALTER ROLE app_readonly SET statement_timeout = '5s';",
    "ALTER ROLE app_readonly SET default_transaction_read_only = on;",
)


def _normalize_database_url(url: str) -> str:
    """Convert standard Neon URLs into an asyncpg-compatible SQLAlchemy URL."""
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url.removeprefix("postgres://")
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url.removeprefix("postgresql://")

    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    sslmode = query.pop("sslmode", None)
    query.pop("channel_binding", None)
    if sslmode is not None and "ssl" not in query:
        # asyncpg accepts `ssl`; libpq's `sslmode` is not a valid asyncpg kwarg.
        query["ssl"] = "false" if sslmode == "disable" else "require"

    return urlunsplit(parsed._replace(query=urlencode(query)))


def get_database_url() -> str:
    database_url = os.getenv(DATABASE_URL_ENV)
    if not database_url:
        raise RuntimeError(
            f"{DATABASE_URL_ENV} is not configured. Expected a Neon PostgreSQL URL."
        )
    return _normalize_database_url(database_url)


def build_async_engine(database_url: str | None = None) -> AsyncEngine:
    """Create the application async engine with conservative production defaults."""
    return create_async_engine(
        _normalize_database_url(database_url or get_database_url()),
        echo=os.getenv("SQLALCHEMY_ECHO", "").lower() == "true",
        pool_pre_ping=True,
        pool_size=int(os.getenv("DATABASE_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("DATABASE_MAX_OVERFLOW", "10")),
        pool_recycle=int(os.getenv("DATABASE_POOL_RECYCLE_SECONDS", "1800")),
        connect_args={
            "server_settings": {
                "application_name": os.getenv(
                    "DATABASE_APPLICATION_NAME", "talentforge-api"
                ),
                "statement_timeout": os.getenv(
                    "DATABASE_STATEMENT_TIMEOUT_MS",
                    str(DEFAULT_STATEMENT_TIMEOUT_MS),
                ),
            }
        },
    )


async_engine = build_async_engine()

session_factory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transaction-bound session for scripts and background workers."""
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields one clean async session per request."""
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_all_tables(engine: AsyncEngine = async_engine) -> None:
    """Create SQLModel tables. Prefer Alembic migrations for evolving production DBs."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def execute_sql_statements(
    statements: Sequence[str],
    engine: AsyncEngine = async_engine,
) -> None:
    """Execute small administrative SQL batches safely through SQLAlchemy text."""
    async with engine.begin() as conn:
        for statement in statements:
            await conn.execute(text(statement))


async def init_pgvector_extension(engine: AsyncEngine = async_engine) -> None:
    """
    Initialize pgvector before vector columns are created.

    PostgreSQL registers pgvector as the `vector` extension. The second command is
    kept as an explicit fallback for environments that expose the extension under
    the package-style name requested by deployment runbooks.
    """
    last_error: Exception | None = None
    for statement in PGVECTOR_EXTENSION_SQL_CANDIDATES:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(statement))
            return
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error


async def init_readonly_role(engine: AsyncEngine = async_engine) -> None:
    """
    Create and harden the app_readonly role.

    This requires a database owner/admin connection. On Neon, run it from a privileged
    migration/admin context, then grant membership or credentials outside this module.
    """
    await execute_sql_statements(APP_READONLY_ROLE_SQL, engine)


async def init_database(
    engine: AsyncEngine = async_engine,
    *,
    create_tables: bool = True,
    create_readonly_role: bool = False,
) -> None:
    """
    Initialize database primitives in dependency order.

    Role creation is disabled by default because hosted databases usually require
    elevated privileges distinct from the runtime application role.
    """
    await init_pgvector_extension(engine)
    if create_tables:
        await create_all_tables(engine)
    if create_readonly_role:
        await init_readonly_role(engine)


async def close_database(engine: AsyncEngine = async_engine) -> None:
    """Dispose pooled connections during FastAPI shutdown."""
    await engine.dispose()
