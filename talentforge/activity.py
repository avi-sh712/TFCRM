"""Workspace-scoped operational activity for the CRM dashboard."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from talentforge.auth import get_current_user
from talentforge.db.database import get_db_session
from talentforge.db.models import (
    AgentAuditLog,
    AgentRun,
    Campaign,
    CustomerProfile,
    ImportJob,
    User,
    WebhookEvent,
)


router = APIRouter(prefix="/api/activity", tags=["activity"])
CurrentUser = Annotated[User, Depends(get_current_user())]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


def _item(
    item_id: str,
    kind: str,
    title: str,
    detail: str,
    timestamp: datetime,
    status: str,
) -> dict[str, str]:
    return {
        "id": item_id,
        "kind": kind,
        "title": title,
        "detail": detail,
        "timestamp": timestamp.isoformat(),
        "status": status,
    }


@router.get("")
async def list_workspace_activity(
    session: DatabaseSession,
    current_user: CurrentUser,
) -> dict[str, list[dict[str, str]]]:
    """Return a concise, tenant-safe feed of CRM and AI operational changes."""
    runs = list((await session.execute(
        select(AgentRun)
        .where(AgentRun.company_id == current_user.id)
        .order_by(AgentRun.created_at.desc())
        .limit(12)
    )).scalars().all())
    campaigns = list((await session.execute(
        select(Campaign)
        .where(Campaign.company_id == current_user.id)
        .order_by(Campaign.created_at.desc())
        .limit(8)
    )).scalars().all())
    imports = list((await session.execute(
        select(ImportJob)
        .where(ImportJob.company_id == current_user.id)
        .order_by(ImportJob.created_at.desc())
        .limit(8)
    )).scalars().all())
    events = list((await session.execute(
        select(WebhookEvent)
        .where(WebhookEvent.company_id == current_user.id)
        .order_by(WebhookEvent.created_at.desc())
        .limit(8)
    )).scalars().all())
    customer_ids = [str(customer_id) for customer_id in (await session.execute(
        select(CustomerProfile.id).where(CustomerProfile.company_id == current_user.id)
    )).scalars().all()]
    audits: list[AgentAuditLog] = []
    if customer_ids:
        audits = list((await session.execute(
            select(AgentAuditLog)
            .where(AgentAuditLog.session_id.in_(customer_ids))
            .order_by(AgentAuditLog.timestamp.desc())
            .limit(8)
        )).scalars().all())

    items: list[dict[str, str]] = []
    for run in runs:
        timestamp = run.completed_at or run.started_at or run.created_at
        items.append(_item(
            f"run-{run.id}", "ai", f"AI {run.type.replace('_', ' ')}",
            "Completed a customer analysis." if run.status == "complete" else f"Run is {run.status}.",
            timestamp, run.status,
        ))
    for audit in audits:
        items.append(_item(
            f"audit-{audit.id}", "ai", f"AI step: {audit.node_name.replace('_', ' ')}",
            audit.action_taken.replace("_", " ") + ".", audit.timestamp, "complete",
        ))
    for campaign in campaigns:
        items.append(_item(
            f"campaign-{campaign.id}", "campaign", "Campaign updated",
            f"{campaign.name} is {campaign.status.replace('_', ' ')}.", campaign.created_at, campaign.status,
        ))
    for job in imports:
        timestamp = job.completed_at or job.started_at or job.created_at
        detail = f"{job.rows_imported} customers added." if job.status == "complete" else f"Import is {job.status}."
        items.append(_item(f"import-{job.id}", "import", "Customer import", detail, timestamp, job.status))
    for event in events:
        items.append(_item(
            f"event-{event.id}", "store", "Connected data received",
            event.event_type.replace("_", " ") + ".", event.created_at, "complete",
        ))

    items.sort(key=lambda item: item["timestamp"], reverse=True)
    return {"items": items[:24]}
