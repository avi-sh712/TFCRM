"""Primary FastAPI execution context for TalentForge."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Final

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from talentforge.auth import router as auth_router
from talentforge.admin import router as admin_router
from talentforge.activity import router as activity_router
from talentforge.agents import router as agents_router
from talentforge.agents import agent_run_dispatcher
from talentforge.campaigns import router as campaigns_router
from talentforge.customers import router as customers_router
from talentforge.deals import router as deals_router
from talentforge.db.database import close_database, init_database
from talentforge.ingestion import router as ingestion_router
from talentforge.integrations import router as integrations_router
from talentforge.integrations import import_job_dispatcher
from talentforge.stats import router as stats_router


logger = logging.getLogger("talentforge.api")

APP_NAME: Final = "TalentForge API"
APP_VERSION: Final = "0.1.0"
PRODUCTION_FRONTEND_ORIGIN_ENV: Final = "FRONTEND_URL"
DEFAULT_PRODUCTION_FRONTEND_ORIGIN: Final = "https://talentforge.vercel.app"


def _allowed_origins() -> list[str]:
    origins: list[str] = [
        # Always allow local Vite dev server
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ]
    # Add production origin if configured and valid
    prod = os.getenv(
        PRODUCTION_FRONTEND_ORIGIN_ENV,
        os.getenv("TALENTFORGE_PRODUCTION_FRONTEND_ORIGIN", DEFAULT_PRODUCTION_FRONTEND_ORIGIN),
    ).strip()
    if prod.startswith("https://") and not prod.endswith("/"):
        origins.append(prod)
    return origins


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
    await agent_run_dispatcher.start()
    await import_job_dispatcher.start()
    try:
        yield
    finally:
        await agent_run_dispatcher.stop()
        await import_job_dispatcher.stop()
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
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-TalentForge-Signature",
        "X-TalentForge-Webhook-Signature",
    ],
    expose_headers=["X-Request-ID"],
    max_age=600,
)

app.include_router(ingestion_router)
app.include_router(auth_router)
app.include_router(campaigns_router)
app.include_router(customers_router)
app.include_router(deals_router)
app.include_router(agents_router)
app.include_router(integrations_router)
app.include_router(admin_router)
app.include_router(activity_router)
app.include_router(stats_router)

static_dir = Path(os.getenv("TALENTFORGE_STATIC_DIR", "talentforge/static"))
app.mount("/assets", StaticFiles(directory=static_dir / "assets", check_dir=False), name="assets")


@app.get("/healthz", include_in_schema=False)
async def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": "talentforge-api"}


@app.get("/{path:path}", include_in_schema=False)
async def frontend(request: Request, path: str) -> FileResponse:
    if path.startswith("api/") or path.startswith("ws/"):
        raise HTTPException(status_code=404, detail="Not found.")
    index_file = static_dir / "index.html"
    if index_file.is_file() and request.method == "GET":
        return FileResponse(index_file)
    raise HTTPException(status_code=404, detail="Not found.")
