"""Admin-only company and system oversight endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from talentforge.auth import require_admin
from talentforge.db.database import get_db_session
from talentforge.db.models import AgentRun, Campaign, CustomerProfile, User, UserRole


router = APIRouter(prefix="/api/admin", tags=["admin"])
AdminUser = Annotated[User, Depends(require_admin())]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


class PlanUpdate(BaseModel):
    plan: str = Field(min_length=1, max_length=50)


class RoleUpdate(BaseModel):
    role: UserRole


class AdminUserResponse(BaseModel):
    id: UUID
    email: str
    role: UserRole
    company_name: str | None
    plan: str
    suspended: bool


def _safe_user(user: User) -> AdminUserResponse:
    return AdminUserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        company_name=user.company_name,
        plan=user.plan,
        suspended=user.suspended,
    )


async def _company_or_404(session: AsyncSession, company_id: UUID) -> User:
    company = await session.get(User, company_id)
    if company is None or company.role != UserRole.COMPANY:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")
    return company


@router.get("/companies")
async def list_companies(session: DatabaseSession, _: AdminUser) -> list[dict[str, object]]:
    result = await session.execute(select(User).where(User.role == UserRole.COMPANY).order_by(User.created_at.desc()))
    companies = list(result.scalars().all())
    items = []
    for company in companies:
        customer_count = await session.scalar(select(func.count(CustomerProfile.id)).where(CustomerProfile.company_id == company.id))
        run_count = await session.scalar(select(func.count(AgentRun.id)).where(AgentRun.company_id == company.id))
        campaign_count = await session.scalar(select(func.count(Campaign.id)).where(Campaign.company_id == company.id))
        items.append({"company": _safe_user(company), "customer_count": customer_count or 0, "agent_run_count": run_count or 0, "campaign_count": campaign_count or 0})
    return items


@router.get("/companies/{company_id}")
async def get_company(company_id: UUID, session: DatabaseSession, _: AdminUser) -> dict[str, object]:
    company = await _company_or_404(session, company_id)
    customers = await session.execute(select(CustomerProfile).where(CustomerProfile.company_id == company_id))
    runs = await session.execute(select(AgentRun).where(AgentRun.company_id == company_id).order_by(AgentRun.created_at.desc()).limit(50))
    campaigns = await session.execute(select(Campaign).where(Campaign.company_id == company_id).order_by(Campaign.created_at.desc()).limit(50))
    return {"company": _safe_user(company), "customers": list(customers.scalars().all()), "agent_runs": list(runs.scalars().all()), "campaigns": list(campaigns.scalars().all())}


@router.patch("/companies/{company_id}/suspend", response_model=AdminUserResponse)
async def suspend_company(company_id: UUID, session: DatabaseSession, _: AdminUser) -> AdminUserResponse:
    company = await _company_or_404(session, company_id)
    company.suspended = True
    await session.commit()
    await session.refresh(company)
    return _safe_user(company)


@router.patch("/companies/{company_id}/restore", response_model=AdminUserResponse)
async def restore_company(company_id: UUID, session: DatabaseSession, _: AdminUser) -> AdminUserResponse:
    company = await _company_or_404(session, company_id)
    company.suspended = False
    await session.commit()
    await session.refresh(company)
    return _safe_user(company)


@router.patch("/companies/{company_id}/plan", response_model=AdminUserResponse)
async def update_company_plan(company_id: UUID, payload: PlanUpdate, session: DatabaseSession, _: AdminUser) -> AdminUserResponse:
    company = await _company_or_404(session, company_id)
    company.plan = payload.plan
    await session.commit()
    await session.refresh(company)
    return _safe_user(company)


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(session: DatabaseSession, _: AdminUser) -> list[AdminUserResponse]:
    result = await session.execute(select(User).order_by(User.created_at.desc()).limit(200))
    return [_safe_user(user) for user in result.scalars().all()]


@router.patch("/users/{user_id}/role", response_model=AdminUserResponse)
async def update_user_role(user_id: UUID, payload: RoleUpdate, session: DatabaseSession, _: AdminUser) -> AdminUserResponse:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    user.role = payload.role
    await session.commit()
    await session.refresh(user)
    return _safe_user(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: UUID, session: DatabaseSession, current_admin: AdminUser) -> None:
    if user_id == current_admin.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An admin cannot delete their own account.")
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    await session.delete(user)
    await session.commit()


@router.get("/system-stats")
async def system_stats(session: DatabaseSession, _: AdminUser) -> dict[str, int]:
    total_runs = await session.scalar(select(func.count(AgentRun.id))) or 0
    credits_used = await session.scalar(select(func.coalesce(func.sum(AgentRun.credits_used), 0))) or 0
    active_companies = await session.scalar(select(func.count(User.id)).where(User.role == UserRole.COMPANY, User.suspended.is_(False))) or 0
    return {"total_runs": int(total_runs), "total_credits_used": int(credits_used), "active_companies": int(active_companies)}
