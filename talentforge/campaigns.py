"""Human review endpoints for pending customer outreach campaigns."""

from __future__ import annotations

from html import escape
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from talentforge.auth import get_current_active_user
from talentforge.db.database import get_db_session
from talentforge.db.models import CampaignStatus, CustomerProfile, OutreachCampaign, User, UserRole
from talentforge.email_service import send_outreach_email


router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

CampaignReviewer = Annotated[
    User,
    Depends(
        get_current_active_user([UserRole.CSM.value, UserRole.ADMIN.value])
    ),
]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


class CampaignReviewRequest(BaseModel):
    status: Literal["approved", "rejected"]
    draft_content: str | None = Field(default=None, min_length=1)


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
