"""Primary FastAPI execution context for TalentForge."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Final

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from talentforge.campaigns import router as campaigns_router
from talentforge.db.database import close_database, init_database
from talentforge.ingestion import router as ingestion_router


logger = logging.getLogger("talentforge.api")

APP_NAME: Final = "TalentForge API"
APP_VERSION: Final = "0.1.0"
PRODUCTION_FRONTEND_ORIGIN_ENV: Final = "TALENTFORGE_PRODUCTION_FRONTEND_ORIGIN"
DEFAULT_PRODUCTION_FRONTEND_ORIGIN: Final = "https://talentforge.vercel.app"


def _production_frontend_origin() -> str:
    origin = os.getenv(
        PRODUCTION_FRONTEND_ORIGIN_ENV,
        DEFAULT_PRODUCTION_FRONTEND_ORIGIN,
    ).strip()
    if not origin.startswith("https://") or origin.endswith("/"):
        raise RuntimeError(
            f"{PRODUCTION_FRONTEND_ORIGIN_ENV} must be a single HTTPS origin without a trailing slash."
        )
    return origin


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    if os.getenv("TALENTFORGE_INIT_DB_ON_STARTUP", "").lower() == "true":
        await init_database(
            create_tables=os.getenv("TALENTFORGE_CREATE_TABLES_ON_STARTUP", "true").lower()
            == "true",
            create_readonly_role=os.getenv(
                "TALENTFORGE_CREATE_READONLY_ROLE_ON_STARTUP",
                "",
            ).lower()
            == "true",
        )
    try:
        yield
    finally:
        await close_database()


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[_production_frontend_origin()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-TalentForge-Signature",
    ],
    expose_headers=["X-Request-ID"],
    max_age=600,
)

app.include_router(ingestion_router)
app.include_router(campaigns_router)


@app.get("/healthz", include_in_schema=False)
async def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": "talentforge-api"}
