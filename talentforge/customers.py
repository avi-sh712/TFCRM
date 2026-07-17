"""Company-scoped customer CRM and health endpoints."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from talentforge.auth import get_current_active_user, get_current_user, workspace_id_for
from talentforge.db.database import get_db_session
from talentforge.db.models import (
    CampaignStatus,
    CustomerHealthHistory,
    CustomerProfile,
    InteractionHistory,
    OutreachCampaign,
    User,
)
from talentforge.graph_engine import score_customer_risk


router = APIRouter(prefix="/api/customers", tags=["customers"])
CurrentUser = Annotated[User, Depends(get_current_user())]
WorkspaceEditor = Annotated[User, Depends(get_current_active_user(["company", "csm", "admin"]))]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=32)
    status: str = Field(default="healthy", max_length=32)
    health_score: float = Field(default=80, ge=0, le=100)
    mrr: float = Field(default=0, ge=0)
    lifetime_value: float = Field(default=0, ge=0)
    purchase_count: int = Field(default=0, ge=0)
    tags: list[str] | None = None
    notes: str | None = None


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=32)
    status: str | None = Field(default=None, max_length=32)
    health_score: float | None = Field(default=None, ge=0, le=100)
    mrr: float | None = Field(default=None, ge=0)
    lifetime_value: float | None = Field(default=None, ge=0)
    purchase_count: int | None = Field(default=None, ge=0)
    tags: list[str] | None = None
    notes: str | None = None


class InteractionCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=100)
    details: dict[str, Any] = Field(default_factory=dict)


async def _owned_customer(
    session: AsyncSession,
    customer_id: UUID,
    user: User,
) -> CustomerProfile:
    customer = await session.get(CustomerProfile, customer_id)
    if customer is None or customer.company_id != workspace_id_for(user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    return customer


@router.get("")
async def list_customers(
    session: DatabaseSession,
    current_user: CurrentUser,
    status_filter: str | None = Query(default=None, alias="status"),
    tag: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    statement = select(CustomerProfile).where(CustomerProfile.company_id == workspace_id_for(current_user))
    if status_filter:
        statement = statement.where(CustomerProfile.status == status_filter)
    if tag:
        statement = statement.where(CustomerProfile.tags.any(tag))

    result = await session.execute(
        statement.order_by(CustomerProfile.updated_at.desc()).offset(offset).limit(limit)
    )
    customers = list(result.scalars().all())
    customer_ids = [customer.id for customer in customers]
    campaign_counts: dict[UUID, int] = {}
    last_interactions: dict[UUID, object] = {}
    if customer_ids:
        campaign_result = await session.execute(
            select(OutreachCampaign.customer_id, func.count(OutreachCampaign.id))
            .where(OutreachCampaign.customer_id.in_(customer_ids))
            .where(OutreachCampaign.status.in_([CampaignStatus.PENDING_REVIEW, CampaignStatus.APPROVED]))
            .group_by(OutreachCampaign.customer_id)
        )
        campaign_counts = {customer_id: count for customer_id, count in campaign_result.all()}
        interaction_result = await session.execute(
            select(InteractionHistory.customer_id, func.max(InteractionHistory.timestamp))
            .where(InteractionHistory.customer_id.in_(customer_ids))
            .group_by(InteractionHistory.customer_id)
        )
        last_interactions = {customer_id: timestamp for customer_id, timestamp in interaction_result.all()}

    return {
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "customer_id": str(customer.id),
                "name": customer.company_name,
                "email": customer.contact_email,
                "phone": customer.phone,
                "status": customer.status,
                "health_score": customer.health_score,
                "mrr": customer.mrr,
                "lifetime_value": customer.lifetime_value,
                "purchase_count": customer.purchase_count,
                "last_purchase_at": customer.last_purchase_at,
                "tags": customer.tags or [],
                "last_interaction_at": last_interactions.get(customer.id),
                "active_campaign_count": campaign_counts.get(customer.id, 0),
            }
            for customer in customers
        ],
    }


@router.post("", response_model=CustomerProfile, status_code=status.HTTP_201_CREATED)
async def create_customer(
    payload: CustomerCreate,
    session: DatabaseSession,
    current_user: WorkspaceEditor,
) -> CustomerProfile:
    customer = CustomerProfile(
        company_id=workspace_id_for(current_user),
        company_name=payload.name,
        contact_email=payload.email,
        phone=payload.phone,
        status=payload.status,
        health_score=payload.health_score,
        mrr=payload.mrr,
        lifetime_value=payload.lifetime_value,
        purchase_count=payload.purchase_count,
        tags=payload.tags,
        notes=payload.notes,
    )
    session.add(customer)
    await session.flush()
    session.add(CustomerHealthHistory(customer_id=customer.id, health_score=customer.health_score, reason="Customer created."))
    await session.commit()
    await session.refresh(customer)
    return customer


@router.get("/{customer_id}", response_model=CustomerProfile)
async def get_customer(
    customer_id: UUID,
    session: DatabaseSession,
    current_user: WorkspaceEditor,
) -> CustomerProfile:
    return await _owned_customer(session, customer_id, current_user)


@router.patch("/{customer_id}", response_model=CustomerProfile)
async def update_customer(
    customer_id: UUID,
    payload: CustomerUpdate,
    session: DatabaseSession,
    current_user: WorkspaceEditor,
) -> CustomerProfile:
    customer = await _owned_customer(session, customer_id, current_user)
    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates:
        customer.company_name = updates.pop("name")
    previous_score = customer.health_score
    for field_name, value in updates.items():
        setattr(customer, field_name if field_name != "email" else "contact_email", value)
    if payload.health_score is not None and payload.health_score != previous_score:
        session.add(
            CustomerHealthHistory(
                customer_id=customer.id,
                health_score=payload.health_score,
                reason="Manual customer update.",
            )
        )
    await session.commit()
    await session.refresh(customer)
    return customer


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: UUID,
    session: DatabaseSession,
    current_user: WorkspaceEditor,
) -> Response:
    customer = await _owned_customer(session, customer_id, current_user)
    await session.delete(customer)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{customer_id}/health-history")
async def get_health_history(
    customer_id: UUID,
    session: DatabaseSession,
    current_user: WorkspaceEditor,
) -> dict[str, object]:
    await _owned_customer(session, customer_id, current_user)
    result = await session.execute(
        select(CustomerHealthHistory)
        .where(CustomerHealthHistory.customer_id == customer_id)
        .order_by(CustomerHealthHistory.recorded_at.asc())
    )
    return {"customer_id": str(customer_id), "items": list(result.scalars().all())}


@router.get("/{customer_id}/interactions")
async def list_customer_interactions(
    customer_id: UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    await _owned_customer(session, customer_id, current_user)
    result = await session.execute(
        select(InteractionHistory)
        .where(InteractionHistory.customer_id == customer_id)
        .order_by(InteractionHistory.timestamp.desc())
        .offset(offset)
        .limit(limit)
    )
    return {"limit": limit, "offset": offset, "items": list(result.scalars().all())}


@router.post("/{customer_id}/interactions", response_model=InteractionHistory, status_code=status.HTTP_201_CREATED)
async def create_customer_interaction(
    customer_id: UUID,
    payload: InteractionCreate,
    session: DatabaseSession,
    current_user: WorkspaceEditor,
) -> InteractionHistory:
    customer = await _owned_customer(session, customer_id, current_user)
    interaction = InteractionHistory(
        customer_id=customer.id,
        event_type=payload.event_type,
        raw_payload=json.dumps(payload.details, ensure_ascii=True),
    )
    customer.last_contact = datetime.now(timezone.utc)
    session.add(interaction)
    await session.commit()
    await session.refresh(interaction)
    return interaction


@router.post("/{customer_id}/score-risk")
async def score_customer_risk_endpoint(
    customer_id: UUID,
    session: DatabaseSession,
    current_user: WorkspaceEditor,
) -> dict[str, object]:
    await _owned_customer(session, customer_id, current_user)
    return await score_customer_risk(customer_id, session)
