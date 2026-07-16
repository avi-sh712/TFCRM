"""Authenticated execution and inspection endpoints for CRM agent runs."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import suppress
from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update
from sqlmodel import select

from talentforge.auth import get_current_user
from talentforge.db.database import get_db_session, session_scope
from talentforge.db.models import AgentRun, User
from talentforge.graph_engine import postgres_checkpointer, run_company_agent
from talentforge.ingestion import agent_stream_manager


router = APIRouter(prefix="/api/agents", tags=["agents"])
logger = logging.getLogger("talentforge.agents")
CurrentUser = Annotated[User, Depends(get_current_user())]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
AgentType = Literal["churn_analysis", "root_cause", "outreach_draft", "health_scoring"]
DISPATCH_POLL_SECONDS = 3.0
DEFAULT_AGENT_RUN_TIMEOUT_SECONDS = 180.0


def _agent_run_timeout_seconds() -> float:
    try:
        timeout = float(os.getenv("TALENTFORGE_AGENT_RUN_TIMEOUT_SECONDS", str(DEFAULT_AGENT_RUN_TIMEOUT_SECONDS)))
    except ValueError:
        return DEFAULT_AGENT_RUN_TIMEOUT_SECONDS
    return timeout if timeout > 0 else DEFAULT_AGENT_RUN_TIMEOUT_SECONDS


class AgentRunDispatcher:
    """Poll persisted queued runs so reloads do not strand background work."""

    def __init__(self) -> None:
        self._stop_event = asyncio.Event()
        self._loop_task: asyncio.Task[None] | None = None
        self._active_tasks: dict[UUID, asyncio.Task[None]] = {}

    async def start(self) -> None:
        if self._loop_task is None or self._loop_task.done():
            self._stop_event.clear()
            self._loop_task = asyncio.create_task(self._poll(), name="agent-run-dispatcher")

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

    async def submit(self, run_id: UUID) -> None:
        existing = self._active_tasks.get(run_id)
        if existing is not None and not existing.done():
            return
        task = asyncio.create_task(_execute_agent_run(run_id), name=f"agent-run-{run_id}")
        self._active_tasks[run_id] = task
        task.add_done_callback(lambda completed: self._active_tasks.pop(run_id, None))

    async def cancel(self, run_id: UUID) -> None:
        task = self._active_tasks.get(run_id)
        if task is not None and not task.done():
            task.cancel()

    async def _poll(self) -> None:
        while not self._stop_event.is_set():
            try:
                async with session_scope() as session:
                    result = await session.execute(
                        select(AgentRun.id).where(AgentRun.status == "queued").limit(25)
                    )
                    queued_ids = list(result.scalars().all())
                for run_id in queued_ids:
                    await self.submit(run_id)
            except Exception:
                logger.exception("agent_run_dispatcher_poll_failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=DISPATCH_POLL_SECONDS)
            except TimeoutError:
                pass


agent_run_dispatcher = AgentRunDispatcher()


class AgentRunRequest(BaseModel):
    type: AgentType
    company_id: UUID | None = None
    config: dict[str, Any] = Field(default_factory=dict)


async def _execute_agent_run(run_id: UUID) -> None:
    """Claim a queued run exactly once, execute it, then persist its terminal state."""
    try:
        async with session_scope() as session:
            claim = await session.execute(
                update(AgentRun)
                .where(AgentRun.id == run_id, AgentRun.status == "queued")
                .values(status="running", started_at=datetime.now(timezone.utc))
                .returning(AgentRun.id)
            )
            if claim.scalar_one_or_none() is None:
                return

        await agent_stream_manager.broadcast_agent_update(
            str(run_id), "agent_run_started", {"run_id": str(run_id)}
        )
        async with session_scope() as session:
            run = await session.get(AgentRun, run_id)
            if run is None or run.status == "cancelled":
                return
            async with postgres_checkpointer() as checkpointer:
                output = await asyncio.wait_for(
                    run_company_agent(
                        run.type,
                        run.company_id,
                        run.input or {},
                        session,
                        checkpointer=checkpointer,
                        thread_id=str(run.id),
                    ),
                    timeout=_agent_run_timeout_seconds(),
                )
            await session.refresh(run)
            if run.status == "cancelled":
                return
            run.output = output
            run.status = "complete"
            run.completed_at = datetime.now(timezone.utc)
            await agent_stream_manager.broadcast_agent_update(
                str(run_id), "agent_run_complete", {"run_id": str(run_id), "type": run.type}
            )
    except TimeoutError:
        async with session_scope() as session:
            run = await session.get(AgentRun, run_id)
            if run is None or run.status == "cancelled":
                return
            run.output = {"message": "Agent run timed out. Reduce the customer selection or retry."}
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
        await agent_stream_manager.broadcast_agent_update(
            str(run_id), "agent_run_failed", {"run_id": str(run_id)}
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("agent_run_failed run_id=%s", run_id)
        async with session_scope() as session:
            run = await session.get(AgentRun, run_id)
            if run is None or run.status == "cancelled":
                return
            run.output = {"message": "Agent run failed. Review configuration and retry."}
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
        await agent_stream_manager.broadcast_agent_update(
            str(run_id), "agent_run_failed", {"run_id": str(run_id)}
        )


@router.post("/run", response_model=AgentRun, status_code=status.HTTP_202_ACCEPTED)
async def create_agent_run(
    payload: AgentRunRequest,
    background_tasks: BackgroundTasks,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> AgentRun:
    company_id = payload.company_id or current_user.id
    if company_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Company scope mismatch.")
    run = AgentRun(company_id=company_id, type=payload.type, input=payload.config)
    session.add(run)
    await session.commit()
    await session.refresh(run)
    background_tasks.add_task(agent_run_dispatcher.submit, run.id)
    return run


@router.get("/runs", response_model=list[AgentRun])
async def list_agent_runs(session: DatabaseSession, current_user: CurrentUser) -> list[AgentRun]:
    result = await session.execute(
        select(AgentRun)
        .where(AgentRun.company_id == current_user.id)
        .order_by(AgentRun.created_at.desc())
        .limit(100)
    )
    return list(result.scalars().all())


@router.get("/runs/{run_id}", response_model=AgentRun)
async def get_agent_run(
    run_id: UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> AgentRun:
    run = await session.get(AgentRun, run_id)
    if run is None or run.company_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found.")
    return run


@router.post("/runs/{run_id}/cancel", response_model=AgentRun)
async def cancel_agent_run(
    run_id: UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> AgentRun:
    run = await session.get(AgentRun, run_id)
    if run is None or run.company_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found.")
    if run.status not in {"queued", "running"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only queued or running agent runs can be cancelled.")
    run.status = "cancelled"
    run.output = {"message": "Cancelled by user."}
    run.completed_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(run)
    await agent_run_dispatcher.cancel(run_id)
    await agent_stream_manager.broadcast_agent_update(str(run_id), "agent_run_cancelled", {"run_id": str(run_id)})
    return run
