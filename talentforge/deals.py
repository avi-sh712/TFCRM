"""Company-scoped sales pipeline endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from talentforge.auth import get_current_active_user, get_current_user, workspace_id_for
from talentforge.db.database import get_db_session
from talentforge.db.models import CustomerProfile, Deal, DealStage, User


router = APIRouter(prefix="/api/deals", tags=["deals"])
CurrentUser = Annotated[User, Depends(get_current_user())]
WorkspaceEditor = Annotated[User, Depends(get_current_active_user(["company", "csm", "admin"]))]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


class DealCreate(BaseModel):
    customer_id: UUID
    name: str = Field(min_length=1, max_length=255)
    value: float = Field(default=0, ge=0)
    stage: DealStage = DealStage.NEW
    notes: str | None = None
    expected_close_date: datetime | None = None


class DealUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    value: float | None = Field(default=None, ge=0)
    stage: DealStage | None = None
    notes: str | None = None
    expected_close_date: datetime | None = None


async def _owned_deal(session: AsyncSession, deal_id: UUID, user: User) -> Deal:
    deal = await session.get(Deal, deal_id)
    if deal is None or deal.company_id != workspace_id_for(user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found.")
    return deal


@router.get("", response_model=list[Deal])
async def list_deals(
    session: DatabaseSession,
    current_user: CurrentUser,
    stage: DealStage | None = Query(default=None),
) -> list[Deal]:
    statement = select(Deal).where(Deal.company_id == workspace_id_for(current_user))
    if stage is not None:
        statement = statement.where(Deal.stage == stage)
    result = await session.execute(statement.order_by(Deal.updated_at.desc()))
    return list(result.scalars().all())


@router.post("", response_model=Deal, status_code=status.HTTP_201_CREATED)
async def create_deal(
    payload: DealCreate,
    session: DatabaseSession,
    current_user: WorkspaceEditor,
) -> Deal:
    customer = await session.get(CustomerProfile, payload.customer_id)
    if customer is None or customer.company_id != workspace_id_for(current_user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    deal = Deal(company_id=workspace_id_for(current_user), **payload.model_dump())
    session.add(deal)
    await session.commit()
    await session.refresh(deal)
    return deal


@router.patch("/{deal_id}", response_model=Deal)
async def update_deal(
    deal_id: UUID,
    payload: DealUpdate,
    session: DatabaseSession,
    current_user: WorkspaceEditor,
) -> Deal:
    deal = await _owned_deal(session, deal_id, current_user)
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(deal, field_name, value)
    await session.commit()
    await session.refresh(deal)
    return deal
