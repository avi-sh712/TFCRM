"""Company integrations for CSV imports, webhooks, and MCP registrations."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import secrets
from contextlib import suppress
from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from talentforge.auth import get_current_user
from talentforge.db.database import get_db_session, session_scope
from talentforge.db.models import CustomerHealthHistory, CustomerProfile, DataSource, ImportJob, User, WebhookEvent
from talentforge.ingestion import parse_customer_csv


router = APIRouter(prefix="/api/integrations", tags=["integrations"])
logger = logging.getLogger("talentforge.integrations")
CurrentUser = Annotated[User, Depends(get_current_user())]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
WEBHOOK_SIGNATURE_HEADER = "X-TalentForge-Webhook-Signature"
SUPPORTED_WEBHOOK_EVENTS = {"user.login", "user.churn_signal", "subscription.cancelled", "support.ticket.opened"}
IMPORT_DISPATCH_POLL_SECONDS = 3.0


class MCPConnectorRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    server_url: str = Field(min_length=8, max_length=2048)
    allowed_tools: list[str] = Field(default_factory=list)


class WebhookEventIn(BaseModel):
    event_type: str
    customer_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class DataSourceResponse(BaseModel):
    id: UUID
    type: str
    name: str
    status: str
    last_sync: datetime | None
    config: dict[str, Any] | None
    created_at: datetime


class ImportJobResponse(BaseModel):
    id: UUID
    filename: str
    status: str
    rows_imported: int
    rows_skipped: int
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


def _import_job_response(job: ImportJob) -> ImportJobResponse:
    return ImportJobResponse(
        id=job.id,
        filename=job.filename,
        status=job.status,
        rows_imported=job.rows_imported,
        rows_skipped=job.rows_skipped,
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
    )


class ImportJobDispatcher:
    """Persisted CSV import worker that survives browser navigation and API reloads."""

    def __init__(self) -> None:
        self._stop_event = asyncio.Event()
        self._loop_task: asyncio.Task[None] | None = None
        self._active_tasks: dict[UUID, asyncio.Task[None]] = {}

    async def start(self) -> None:
        if self._loop_task is None or self._loop_task.done():
            self._stop_event.clear()
            self._loop_task = asyncio.create_task(self._poll(), name="csv-import-dispatcher")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._loop_task is not None:
            self._loop_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._loop_task
        for task in tuple(self._active_tasks.values()):
            task.cancel()
        if self._active_tasks:
            await asyncio.gather(*self._active_tasks.values(), return_exceptions=True)
        self._active_tasks.clear()

    async def submit(self, job_id: UUID) -> None:
        existing = self._active_tasks.get(job_id)
        if existing is not None and not existing.done():
            return
        task = asyncio.create_task(_process_csv_import(job_id), name=f"csv-import-{job_id}")
        self._active_tasks[job_id] = task
        task.add_done_callback(lambda completed: self._active_tasks.pop(job_id, None))

    async def cancel(self, job_id: UUID) -> None:
        task = self._active_tasks.get(job_id)
        if task is not None and not task.done():
            task.cancel()

    async def _poll(self) -> None:
        while not self._stop_event.is_set():
            try:
                async with session_scope() as session:
                    result = await session.execute(
                        select(ImportJob.id).where(ImportJob.status == "queued").limit(10)
                    )
                    queued_ids = list(result.scalars().all())
                for job_id in queued_ids:
                    await self.submit(job_id)
            except Exception:
                logger.exception("csv_import_dispatcher_poll_failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=IMPORT_DISPATCH_POLL_SECONDS)
            except TimeoutError:
                pass


async def _process_csv_import(job_id: UUID) -> None:
    try:
        async with session_scope() as session:
            claim = await session.execute(
                update(ImportJob)
                .where(ImportJob.id == job_id, ImportJob.status == "queued")
                .values(status="running", started_at=datetime.now(timezone.utc))
                .returning(ImportJob.id)
            )
            if claim.scalar_one_or_none() is None:
                return

        async with session_scope() as session:
            job = await session.get(ImportJob, job_id)
            if job is None or job.status == "cancelled":
                return
            rows, skipped = parse_customer_csv(job.raw_csv)
            for index, row in enumerate(rows, start=1):
                if index % 10 == 0:
                    await session.refresh(job)
                    if job.status == "cancelled":
                        raise asyncio.CancelledError
                customer = CustomerProfile(
                    company_id=job.company_id,
                    company_name=row["name"],
                    contact_email=row["email"],
                    phone=row["phone"],
                    status=row["status"],
                    health_score=80,
                    mrr=row["mrr"],
                    lifetime_value=row["lifetime_value"],
                    purchase_count=row["purchase_count"],
                    tags=row["tags"],
                )
                session.add(customer)
                await session.flush()
                session.add(CustomerHealthHistory(customer_id=customer.id, health_score=80, reason="CSV import."))
            await session.refresh(job)
            if job.status == "cancelled":
                raise asyncio.CancelledError
            job.status = "complete"
            job.rows_imported = len(rows)
            job.rows_skipped = len(skipped)
            job.raw_csv = ""
            job.completed_at = datetime.now(timezone.utc)
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("csv_import_failed job_id=%s", job_id)
        async with session_scope() as session:
            job = await session.get(ImportJob, job_id)
            if job is None or job.status == "cancelled":
                return
            job.status = "failed"
            job.error_message = "CSV import failed. Check the file format and retry."
            job.raw_csv = ""
            job.completed_at = datetime.now(timezone.utc)


import_job_dispatcher = ImportJobDispatcher()


def _source_response(source: DataSource, *, include_webhook_secret: bool = False) -> DataSourceResponse:
    config = dict(source.config or {})
    if not include_webhook_secret:
        config.pop("webhook_secret", None)
    return DataSourceResponse(
        id=source.id,
        type=source.type,
        name=source.name,
        status=source.status,
        last_sync=source.last_sync,
        config=config or None,
        created_at=source.created_at,
    )


@router.post("/csv-upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_csv(
    background_tasks: BackgroundTasks,
    session: DatabaseSession,
    current_user: CurrentUser,
    file: UploadFile = File(...),
) -> ImportJobResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Upload a CSV file.")
    content = (await file.read()).decode("utf-8-sig", errors="replace")
    job = ImportJob(company_id=current_user.id, filename=file.filename[:255], raw_csv=content)
    session.add(job)
    await session.commit()
    await session.refresh(job)
    background_tasks.add_task(import_job_dispatcher.submit, job.id)
    return _import_job_response(job)


@router.get("/csv-jobs", response_model=list[ImportJobResponse])
async def list_csv_jobs(
    session: DatabaseSession,
    current_user: CurrentUser,
) -> list[ImportJobResponse]:
    result = await session.execute(
        select(ImportJob)
        .where(ImportJob.company_id == current_user.id)
        .order_by(ImportJob.created_at.desc())
        .limit(20)
    )
    return [_import_job_response(job) for job in result.scalars().all()]


@router.post("/csv-jobs/{job_id}/cancel", response_model=ImportJobResponse)
async def cancel_csv_job(
    job_id: UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> ImportJobResponse:
    job = await session.get(ImportJob, job_id)
    if job is None or job.company_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found.")
    if job.status not in {"queued", "running"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only queued or running imports can be cancelled.")
    job.status = "cancelled"
    job.error_message = "Cancelled by user."
    job.raw_csv = ""
    job.completed_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(job)
    await import_job_dispatcher.cancel(job_id)
    return _import_job_response(job)


@router.get("", response_model=list[DataSourceResponse])
async def list_integrations(session: DatabaseSession, current_user: CurrentUser) -> list[DataSourceResponse]:
    result = await session.execute(
        select(DataSource)
        .where(DataSource.company_id == current_user.id)
        .order_by(DataSource.created_at.desc())
    )
    return [_source_response(source) for source in result.scalars().all()]


@router.post("/mcp-connector", response_model=DataSourceResponse, status_code=status.HTTP_201_CREATED)
async def register_mcp_connector(
    payload: MCPConnectorRequest,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> DataSourceResponse:
    source = DataSource(
        company_id=current_user.id,
        type="mcp_connector",
        name=payload.name,
        config={"server_url": payload.server_url, "allowed_tools": payload.allowed_tools},
    )
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return _source_response(source)


@router.post("/webhook-source", response_model=DataSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook_source(
    session: DatabaseSession,
    current_user: CurrentUser,
) -> DataSourceResponse:
    source = DataSource(
        company_id=current_user.id,
        type="api_webhook",
        name="Inbound product events",
        config={"webhook_secret": secrets.token_urlsafe(32)},
    )
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return _source_response(source, include_webhook_secret=True)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(
    source_id: UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> None:
    source = await session.get(DataSource, source_id)
    if source is None or source.company_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found.")
    await session.delete(source)
    await session.commit()


@router.post("/webhook/{company_id}", status_code=status.HTTP_202_ACCEPTED)
async def ingest_company_webhook(
    company_id: UUID,
    request: Request,
    session: DatabaseSession,
    signature: Annotated[str | None, Header(alias=WEBHOOK_SIGNATURE_HEADER)] = None,
) -> dict[str, str]:
    raw_body = await request.body()
    sources = await session.execute(
        select(DataSource).where(DataSource.company_id == company_id, DataSource.type == "api_webhook")
    )
    valid_source = None
    for source in sources.scalars().all():
        secret = str((source.config or {}).get("webhook_secret", ""))
        expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        supplied = (signature or "").removeprefix("sha256=")
        if secret and hmac.compare_digest(supplied, expected):
            valid_source = source
            break
    if valid_source is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature.")
    event = WebhookEventIn.model_validate_json(raw_body)
    if event.event_type not in SUPPORTED_WEBHOOK_EVENTS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported webhook event.")
    if event.customer_id is not None:
        customer = await session.get(CustomerProfile, event.customer_id)
        if customer is None or customer.company_id != company_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
        if event.event_type in {"user.churn_signal", "subscription.cancelled"}:
            customer.status = "at_risk"
            customer.health_score = max(0, customer.health_score - 20)
            session.add(CustomerHealthHistory(
                customer_id=customer.id,
                health_score=customer.health_score,
                reason=f"Webhook event: {event.event_type}.",
            ))
    session.add(WebhookEvent(company_id=company_id, customer_id=event.customer_id, event_type=event.event_type, payload=event.payload))
    valid_source.last_sync = datetime.now(timezone.utc)
    await session.commit()
    return {"status": "accepted"}
