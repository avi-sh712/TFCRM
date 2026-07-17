"""Company-owner team management for shared TalentForge workspaces."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from talentforge.auth import (
    get_current_active_user,
    hash_password,
    normalize_username,
    workspace_id_for,
)
from talentforge.db.database import get_db_session
from talentforge.db.models import User, UserRole


router = APIRouter(prefix="/api/team", tags=["team"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
WorkspaceOwner = Annotated[User, Depends(get_current_active_user([UserRole.COMPANY.value]))]
AssignableRole = Literal["csm", "viewer"]


class TeamMemberCreate(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=12)
    role: AssignableRole


class TeamMemberUpdate(BaseModel):
    role: AssignableRole


class TeamMemberResponse(BaseModel):
    id: UUID
    email: str
    username: str | None
    role: UserRole
    created_at: datetime


def _response(member: User) -> TeamMemberResponse:
    return TeamMemberResponse(
        id=member.id,
        email=member.email,
        username=member.username,
        role=member.role,
        created_at=member.created_at,
    )


async def _member_or_404(session: AsyncSession, owner: User, member_id: UUID) -> User:
    member = await session.get(User, member_id)
    if member is None or member.workspace_id != workspace_id_for(owner) or member.id == owner.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team member not found.")
    return member


@router.get("/members", response_model=list[TeamMemberResponse])
async def list_members(session: DatabaseSession, owner: WorkspaceOwner) -> list[TeamMemberResponse]:
    members = (await session.execute(
        select(User).where(User.workspace_id == workspace_id_for(owner)).order_by(User.created_at.asc())
    )).scalars().all()
    return [_response(member) for member in members]


@router.post("/members", response_model=TeamMemberResponse, status_code=status.HTTP_201_CREATED)
async def create_member(
    payload: TeamMemberCreate,
    session: DatabaseSession,
    owner: WorkspaceOwner,
) -> TeamMemberResponse:
    try:
        member = User(
            email=payload.email.lower(),
            username=normalize_username(payload.username),
            hashed_password=hash_password(payload.password),
            role=UserRole(payload.role),
            company_name=owner.company_name,
            workspace_id=workspace_id_for(owner),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
    session.add(member)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account already exists for this email or username.") from None
    await session.refresh(member)
    return _response(member)


@router.patch("/members/{member_id}", response_model=TeamMemberResponse)
async def update_member(
    member_id: UUID,
    payload: TeamMemberUpdate,
    session: DatabaseSession,
    owner: WorkspaceOwner,
) -> TeamMemberResponse:
    member = await _member_or_404(session, owner, member_id)
    member.role = UserRole(payload.role)
    await session.commit()
    await session.refresh(member)
    return _response(member)


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_member(member_id: UUID, session: DatabaseSession, owner: WorkspaceOwner) -> None:
    member = await _member_or_404(session, owner, member_id)
    await session.delete(member)
    await session.commit()
