"""Human review endpoints for pending customer outreach campaigns."""

from __future__ import annotations

from html import escape
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from talentforge.auth import get_current_active_user, get_current_user
from talentforge.db.database import get_db_session, session_scope
from talentforge.db.models import Campaign, CampaignStatus, CustomerProfile, OutreachCampaign, User, UserRole
from talentforge.email_service import send_outreach_email


router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

CampaignReviewer = Annotated[
    User,
    Depends(
        get_current_active_user([UserRole.CSM.value, UserRole.ADMIN.value])
    ),
]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
CampaignOwner = Annotated[User, Depends(get_current_user())]


class CampaignReviewRequest(BaseModel):
    status: Literal["approved", "rejected"]
    draft_content: str | None = Field(default=None, min_length=1)


class CampaignCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    target_segment: dict[str, object] | None = None
    message_template: str | None = None


class CampaignUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    target_segment: dict[str, object] | None = None
    message_template: str | None = None
    status: Literal["draft", "pending_review"] | None = None


async def _owned_campaign(
    session: AsyncSession,
    campaign_id: UUID,
    current_user: User,
) -> Campaign:
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None or campaign.company_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found.")
    return campaign


async def _dispatch_campaign(campaign_id: UUID) -> None:
    async with session_scope() as session:
        campaign = await session.get(Campaign, campaign_id)
        if campaign is None or campaign.status != "active" or not campaign.message_template:
            return
        customer_ids = [UUID(customer_id) for customer_id in (campaign.target_segment or {}).get("customer_ids", [])]
        if not customer_ids:
            return
        customers = await session.execute(select(CustomerProfile).where(CustomerProfile.id.in_(customer_ids)))
        subject = _campaign_subject(campaign.message_template)
        html = _campaign_html(campaign.message_template)
        sent_count = 0
        for customer in customers.scalars().all():
            if customer.contact_email:
                await send_outreach_email(customer.contact_email, subject, html)
                sent_count += 1
        campaign.sent_count += sent_count
        campaign.status = "completed"


@router.get("", response_model=list[Campaign])
async def list_campaigns(
    session: DatabaseSession,
    current_user: CampaignOwner,
    campaign_status: str | None = Query(default=None, alias="status"),
) -> list[Campaign]:
    statement = select(Campaign).where(Campaign.company_id == current_user.id)
    if campaign_status:
        statement = statement.where(Campaign.status == campaign_status)
    result = await session.execute(statement.order_by(Campaign.created_at.desc()))
    return list(result.scalars().all())


@router.post("", response_model=Campaign, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreateRequest,
    session: DatabaseSession,
    current_user: CampaignOwner,
) -> Campaign:
    campaign = Campaign(
        company_id=current_user.id,
        name=payload.name,
        target_segment=payload.target_segment,
        message_template=payload.message_template,
    )
    session.add(campaign)
    await session.commit()
    await session.refresh(campaign)
    return campaign


@router.get("/pending", response_model=list[OutreachCampaign])
async def list_pending_campaigns(
    session: DatabaseSession,
    _: CampaignReviewer,
) -> list[OutreachCampaign]:
    result = await session.execute(
        select(OutreachCampaign)
        .where(OutreachCampaign.status == CampaignStatus.PENDING_REVIEW)
        .order_by(OutreachCampaign.created_at.asc())
    )
    return list(result.scalars().all())


@router.get("/stats")
async def get_campaign_stats(
    session: DatabaseSession,
    _: CampaignReviewer,
) -> dict[str, int]:
    async def count_status(campaign_status: CampaignStatus) -> int:
        result = await session.execute(
            select(func.count())
            .select_from(OutreachCampaign)
            .where(OutreachCampaign.status == campaign_status)
        )
        return int(result.scalar_one())

    total_result = await session.execute(select(func.count()).select_from(OutreachCampaign))
    return {
        "total": int(total_result.scalar_one()),
        "pending": await count_status(CampaignStatus.PENDING_REVIEW),
        "approved": await count_status(CampaignStatus.APPROVED),
        "sent": await count_status(CampaignStatus.SENT),
        "rejected": await count_status(CampaignStatus.REJECTED),
    }


@router.get("/{campaign_id}", response_model=Campaign)
async def get_campaign(
    campaign_id: UUID,
    session: DatabaseSession,
    current_user: CampaignOwner,
) -> Campaign:
    return await _owned_campaign(session, campaign_id, current_user)


@router.patch("/{campaign_id}", response_model=Campaign)
async def update_campaign(
    campaign_id: UUID,
    payload: CampaignUpdateRequest,
    session: DatabaseSession,
    current_user: CampaignOwner,
) -> Campaign:
    campaign = await _owned_campaign(session, campaign_id, current_user)
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(campaign, field_name, value)
    await session.commit()
    await session.refresh(campaign)
    return campaign


@router.patch("/{campaign_id}/approve", response_model=Campaign)
async def approve_campaign(
    campaign_id: UUID,
    background_tasks: BackgroundTasks,
    session: DatabaseSession,
    current_user: CampaignReviewer,
) -> Campaign:
    campaign = await _owned_campaign(session, campaign_id, current_user)
    if campaign.status != "pending_review":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending campaigns can be approved.")
    campaign.status = "active"
    await session.commit()
    await session.refresh(campaign)
    background_tasks.add_task(_dispatch_campaign, campaign.id)
    return campaign


@router.patch("/{campaign_id}/reject", response_model=Campaign)
async def reject_campaign(
    campaign_id: UUID,
    session: DatabaseSession,
    current_user: CampaignOwner,
) -> Campaign:
    campaign = await _owned_campaign(session, campaign_id, current_user)
    campaign.status = "draft"
    await session.commit()
    await session.refresh(campaign)
    return campaign


@router.post("/{campaign_id}/review", response_model=OutreachCampaign)
async def review_campaign(
    campaign_id: UUID,
    review: CampaignReviewRequest,
    session: DatabaseSession,
    current_user: CampaignReviewer,
) -> OutreachCampaign:
    result = await session.execute(
        select(OutreachCampaign)
        .where(OutreachCampaign.id == campaign_id)
        .with_for_update()
    )
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found.",
        )
    if campaign.status != CampaignStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Campaign has already been reviewed.",
        )

    if review.draft_content is not None:
        campaign.draft_content = review.draft_content
    campaign.reviewed_by = current_user.id

    if review.status == "rejected":
        campaign.status = CampaignStatus.REJECTED
        await session.commit()
        await session.refresh(campaign)
        return campaign

    customer = await session.get(CustomerProfile, campaign.customer_id)
    recipient_email = getattr(customer, "contact_email", None) if customer else None
    if not isinstance(recipient_email, str) or not recipient_email.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Customer contact email is unavailable.",
        )

    try:
        await send_outreach_email(
            to_email=recipient_email,
            subject=_campaign_subject(campaign.draft_content),
            html_content=_campaign_html(campaign.draft_content),
        )
    except Exception:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Email delivery failed; the campaign remains pending review.",
        ) from None

    campaign.status = CampaignStatus.SENT
    await session.commit()
    await session.refresh(campaign)
    return campaign


def _campaign_subject(draft_content: str) -> str:
    first_line = draft_content.strip().splitlines()[0] if draft_content.strip() else ""
    if first_line.lower().startswith("subject:"):
        return first_line.partition(":")[2].strip() or "A note from TalentForge"
    return "A note from TalentForge"


def _campaign_html(draft_content: str) -> str:
    return "<br>".join(escape(line) for line in draft_content.splitlines())
