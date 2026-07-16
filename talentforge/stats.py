"""Authenticated dashboard aggregate statistics."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from talentforge.auth import get_current_user
from talentforge.db.database import get_db_session
from talentforge.db.models import AgentAuditLog, AgentRun, CustomerProfile, InteractionHistory, User


router = APIRouter(prefix="/api/stats", tags=["stats"])
CurrentUser = Annotated[User, Depends(get_current_user())]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/cache")
async def cache_stats(session: DatabaseSession, current_user: CurrentUser) -> dict[str, int]:
    cached_entries = await session.scalar(
        select(func.count(InteractionHistory.id))
        .join(CustomerProfile, CustomerProfile.id == InteractionHistory.customer_id)
        .where(CustomerProfile.company_id == current_user.id, InteractionHistory.semantic_signature.is_not(None))
    ) or 0
    cache_hits = await session.scalar(
        select(func.count(AgentAuditLog.id)).where(AgentAuditLog.action_taken == "semantic_cache_hit")
    ) or 0
    return {"cached_resolutions": int(cached_entries), "cache_hits": int(cache_hits)}


@router.get("/overview")
async def overview_stats(session: DatabaseSession, current_user: CurrentUser) -> dict[str, float | int]:
    total_customers = await session.scalar(select(func.count(CustomerProfile.id)).where(CustomerProfile.company_id == current_user.id)) or 0
    healthy_customers = await session.scalar(select(func.count(CustomerProfile.id)).where(CustomerProfile.company_id == current_user.id, CustomerProfile.status == "healthy")) or 0
    active_runs = await session.scalar(select(func.count(AgentRun.id)).where(AgentRun.company_id == current_user.id, AgentRun.status.in_(["queued", "running"]))) or 0
    cache = await cache_stats(session, current_user)
    return {
        "churn_prevention_rate": round((int(healthy_customers) / int(total_customers) * 100) if total_customers else 0, 1),
        "cached_resolutions": cache["cached_resolutions"],
        "active_swarm_runs": int(active_runs),
    }
