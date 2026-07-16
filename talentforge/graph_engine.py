"""Durable, bounded LangGraph orchestration for customer churn mitigation.

The graph deliberately has no email-sending capability. Its terminal success
path persists a pending-review outreach draft; delivery belongs to a separately
authorized Resend service after a human approves the campaign.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Literal, TypedDict
from uuid import UUID
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from talentforge.db.cache_service import check_semantic_cache
from talentforge.db.models import (
    Campaign,
    CustomerHealthHistory,
    AgentAuditLog,
    CampaignStatus,
    CustomerProfile,
    InteractionHistory,
    OutreachCampaign,
)
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool


MAX_TOOL_RETRIES = 3
DEFAULT_FAST_MODEL = "gpt-5.6-luna"
DEFAULT_FRONTIER_MODEL = "gpt-5.6-terra"
DEFAULT_COOLDOWN_HOURS = 24
DEFAULT_TOOL_TIMEOUT_SECONDS = 15.0
DEFAULT_MODEL_TIMEOUT_SECONDS = 45.0
DEFAULT_MAX_TOOL_CALLS = 3
DEFAULT_MAX_TOOL_RESULT_CHARS = 16_000
CHECKPOINTER_MODE_ENV = "TALENTFORGE_CHECKPOINTER_MODE"

logger = logging.getLogger("talentforge.graph_engine")


class TalentForgeGraphState(TypedDict):
    """The complete durable state shape for one customer incident."""

    customer_id: str
    alert_context: dict[str, Any]
    retry_count: int
    max_retries: int
    tool_errors: list[str]
    semantic_cache_hit: bool
    analysis_output: str
    final_draft: str


class CompanyAgentState(TypedDict):
    company_id: str
    config: dict[str, Any]
    output: dict[str, Any]


class RiskAssessment(BaseModel):
    risk_level: str
    drivers: list[str] = Field(default_factory=list)
    recommended_action: str


class CustomerRiskScore(BaseModel):
    customer_id: UUID
    health_score: float = Field(ge=0, le=100)
    reason: str


class ChurnRiskScoringResult(BaseModel):
    scores: list[CustomerRiskScore] = Field(default_factory=list)


class RootCauseReport(BaseModel):
    top_causes: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    urgency: str
    evidence: list[str] = Field(default_factory=list)


class OutreachDraftResult(BaseModel):
    campaign_name: str
    subject: str
    message_template: str
    target_customer_ids: list[UUID] = Field(default_factory=list)


class GraphEngineConfigurationError(RuntimeError):
    """Raised for missing or invalid local graph configuration."""


class GraphEngineDependencyError(RuntimeError):
    """Raised when an optional graph dependency has not been installed."""


@dataclass(frozen=True, slots=True)
class ModelTierSettings:
    """Dynamic OpenAI model and timeout configuration for one graph instance."""

    routing_model: str
    frontier_model: str
    frontier_reasoning_effort: str
    tool_timeout_seconds: float
    model_timeout_seconds: float
    max_tool_calls: int
    max_tool_result_chars: int
    cooldown_hours: int

    @classmethod
    def from_environment(cls) -> "ModelTierSettings":
        return cls(
            routing_model=_environment_value(
                "TALENTFORGE_ROUTING_MODEL", DEFAULT_FAST_MODEL
            ),
            frontier_model=_environment_value(
                "TALENTFORGE_FRONTIER_MODEL", DEFAULT_FRONTIER_MODEL
            ),
            frontier_reasoning_effort=_environment_value(
                "TALENTFORGE_FRONTIER_REASONING_EFFORT", "high"
            ),
            tool_timeout_seconds=_positive_float(
                "TALENTFORGE_MCP_TOOL_TIMEOUT_SECONDS",
                DEFAULT_TOOL_TIMEOUT_SECONDS,
            ),
            model_timeout_seconds=_positive_float(
                "TALENTFORGE_MODEL_TIMEOUT_SECONDS",
                DEFAULT_MODEL_TIMEOUT_SECONDS,
            ),
            max_tool_calls=_positive_int(
                "TALENTFORGE_MAX_MCP_TOOL_CALLS", DEFAULT_MAX_TOOL_CALLS
            ),
            max_tool_result_chars=_positive_int(
                "TALENTFORGE_MAX_MCP_RESULT_CHARS",
                DEFAULT_MAX_TOOL_RESULT_CHARS,
            ),
            cooldown_hours=_positive_int(
                "TALENTFORGE_CUSTOMER_COOLDOWN_HOURS",
                DEFAULT_COOLDOWN_HOURS,
            ),
        )


def make_initial_state(
    customer_id: str,
    alert_context: dict[str, Any],
    *,
    max_retries: int = MAX_TOOL_RETRIES,
) -> TalentForgeGraphState:
    """Create a complete initial state and apply the non-bypassable retry cap."""
    return {
        "customer_id": customer_id,
        "alert_context": alert_context,
        "retry_count": 0,
        "max_retries": _bounded_retry_limit(max_retries),
        "tool_errors": [],
        "semantic_cache_hit": False,
        "analysis_output": "",
        "final_draft": "",
    }


@asynccontextmanager
async def _default_session_scope() -> AsyncIterator[Any]:
    """Delay database initialization until a graph run actually requires it."""
    from talentforge.db.database import session_scope

    async with session_scope() as session:
        yield session


@asynccontextmanager
async def _default_mcp_tool_session() -> AsyncIterator[list[BaseTool]]:
    """Delay MCP configuration and its credentials until tool retrieval."""
    from talentforge.mcp_client import postgres_mcp_tool_session

    async with postgres_mcp_tool_session() as tools:
        yield tools


class TalentForgeGraphEngine:
    """Owns graph nodes and their injected data/model dependencies."""

    def __init__(
        self,
        *,
        settings: ModelTierSettings | None = None,
        cache_session_factory: Callable[[], Any] = _default_session_scope,
        mcp_tool_session_factory: Callable[[], Any] = _default_mcp_tool_session,
        routing_model: Any | None = None,
        frontier_model: Any | None = None,
    ) -> None:
        self._settings = settings or ModelTierSettings.from_environment()
        self._cache_session_factory = cache_session_factory
        self._mcp_tool_session_factory = mcp_tool_session_factory
        self._routing_model = routing_model
        self._frontier_model = frontier_model

    @property
    def settings(self) -> ModelTierSettings:
        return self._settings

    def _models(self) -> tuple[Any, Any]:
        """Create the tiered runners lazily so imports do not require an API key."""
        if self._routing_model is not None and self._frontier_model is not None:
            return self._routing_model, self._frontier_model

        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            raise GraphEngineDependencyError(
                "langchain-openai is required to run the TalentForge graph."
            ) from None

        self._routing_model = self._routing_model or ChatOpenAI(
            model=self.settings.routing_model,
            timeout=self.settings.model_timeout_seconds,
            max_retries=0,
        )
        self._frontier_model = self._frontier_model or ChatOpenAI(
            model=self.settings.frontier_model,
            reasoning_effort=self.settings.frontier_reasoning_effort,
            timeout=self.settings.model_timeout_seconds,
            max_retries=0,
        )
        return self._routing_model, self._frontier_model

    async def check_cache_node(
        self, state: TalentForgeGraphState
    ) -> dict[str, Any]:
        """Return a semantic-cache result or enforce the customer cooldown."""
        retry_limit = _bounded_retry_limit(state["max_retries"])
        embedding = _alert_embedding(state["alert_context"])

        try:
            async with self._cache_session_factory() as session:
                if embedding is not None:
                    cached_draft = await check_semantic_cache(session, embedding)
                    if cached_draft is not None:
                        session.add(
                            AgentAuditLog(
                                session_id=state["customer_id"],
                                node_name="check_cache_node",
                                action_taken="semantic_cache_hit",
                                metadata_json={"customer_id": state["customer_id"]},
                            )
                        )
                        await session.flush()
                        return {
                            "max_retries": retry_limit,
                            "semantic_cache_hit": True,
                            "analysis_output": "A validated semantic playbook was reused.",
                            "final_draft": cached_draft,
                        }

                if await self._customer_in_cooldown(session, state["customer_id"]):
                    return {
                        "max_retries": retry_limit,
                        "semantic_cache_hit": False,
                        "analysis_output": "Customer outreach is within the 24-hour cooldown.",
                        "final_draft": _cooldown_notice(),
                    }
        except Exception:
            # A cache outage must not create an automated retry loop or expose DB details.
            return {
                "max_retries": retry_limit,
                "semantic_cache_hit": False,
                "analysis_output": "Semantic cache unavailable; continuing with guarded retrieval.",
            }

        return {
            "max_retries": retry_limit,
            "semantic_cache_hit": False,
        }

    async def call_mcp_tool_node(
        self, state: TalentForgeGraphState
    ) -> dict[str, Any]:
        """Use Luna to select and invoke approved read-only customer tools."""
        retry_limit = _bounded_retry_limit(state["max_retries"])
        current_retry_count = max(0, _coerce_int(state["retry_count"]))

        try:
            routing_model, _ = self._models()
            async with self._mcp_tool_session_factory() as tools:
                router = routing_model.bind_tools(tools)
                response = await asyncio.wait_for(
                    router.ainvoke(_tool_routing_messages(state)),
                    timeout=self.settings.model_timeout_seconds,
                )
                tool_calls = list(getattr(response, "tool_calls", []) or [])
                if not tool_calls:
                    raise RuntimeError("No read-only tracking tool was selected.")

                available_tools = {tool.name: tool for tool in tools}
                results: list[dict[str, Any]] = []
                for call in tool_calls[: self.settings.max_tool_calls]:
                    tool_name = str(call.get("name", ""))
                    tool = available_tools.get(tool_name)
                    if tool is None:
                        raise RuntimeError("The selected tracking tool is not available.")
                    result = await asyncio.wait_for(
                        tool.ainvoke(call.get("args", {})),
                        timeout=self.settings.tool_timeout_seconds,
                    )
                    results.append({"tool": tool_name, "result": result})

            return {
                "max_retries": retry_limit,
                "tool_errors": [],
                "analysis_output": _bounded_json(
                    results, self.settings.max_tool_result_chars
                ),
            }
        except Exception:
            # Deliberately discard exception text: adapters may include connection details.
            return {
                "max_retries": retry_limit,
                "retry_count": current_retry_count + 1,
                "tool_errors": ["Read-only customer history retrieval failed or timed out."],
                "analysis_output": "",
            }

    async def analyze_root_cause_node(
        self, state: TalentForgeGraphState
    ) -> dict[str, Any]:
        """Use the frontier runner for evidence-bound churn root-cause analysis."""
        try:
            _, frontier_model = self._models()
            response = await asyncio.wait_for(
                frontier_model.ainvoke(_root_cause_messages(state)),
                timeout=self.settings.model_timeout_seconds,
            )
            return {"analysis_output": _message_text(response)}
        except Exception:
            return {
                "analysis_output": (
                    "Automated root-cause analysis is unavailable. Treat the alert and "
                    "retrieved history as evidence for human review only."
                )
            }

    async def draft_email_node(
        self, state: TalentForgeGraphState
    ) -> dict[str, Any]:
        """Draft and stage outreach without granting the graph email-sending authority."""
        try:
            async with self._cache_session_factory() as session:
                if await self._customer_in_cooldown(session, state["customer_id"]):
                    return {
                        "final_draft": _cooldown_notice(),
                        "analysis_output": "Outreach suppressed by the 24-hour customer cooldown.",
                    }

            routing_model, frontier_model = self._models()
            frontier_response = await asyncio.wait_for(
                frontier_model.ainvoke(_outreach_drafting_messages(state)),
                timeout=self.settings.model_timeout_seconds,
            )
            frontier_draft = _message_text(frontier_response)
            formatted_response = await asyncio.wait_for(
                routing_model.ainvoke(_formatting_messages(frontier_draft)),
                timeout=self.settings.model_timeout_seconds,
            )
            final_draft = _message_text(formatted_response)
            await self._stage_pending_review_campaign(state, final_draft)
            return {"final_draft": final_draft}
        except Exception:
            fallback = _human_review_draft()
            try:
                await self._stage_pending_review_campaign(state, fallback)
            except Exception:
                pass
            return {
                "final_draft": fallback,
                "analysis_output": (
                    "Automated drafting was unavailable; a baseline human-review item "
                    "was prepared without sending email."
                ),
            }

    async def escalate_to_human_node(
        self, state: TalentForgeGraphState
    ) -> dict[str, Any]:
        """Create a non-sending fallback audit item after the hard retry ceiling."""
        retry_limit = _bounded_retry_limit(state["max_retries"])
        final_draft = _human_review_draft()
        try:
            async with self._cache_session_factory() as session:
                session.add(
                    AgentAuditLog(
                        session_id=state["customer_id"],
                        node_name="escalate_to_human_node",
                        action_taken="mcp_retry_ceiling_reached",
                        metadata_json={
                            "retry_count": max(0, _coerce_int(state["retry_count"])),
                            "max_retries": retry_limit,
                            "tool_errors": list(state["tool_errors"]),
                            "email_sent": False,
                        },
                    )
                )
                await session.flush()
        except Exception:
            # The graph still terminates; it must never retry an escalation failure.
            return {
                "max_retries": retry_limit,
                "final_draft": final_draft,
                "analysis_output": "Human review required; escalation audit persistence is unavailable.",
            }

        return {
            "max_retries": retry_limit,
            "final_draft": final_draft,
            "analysis_output": "Human review required after the MCP retry ceiling.",
        }

    def compile(self, checkpointer: Any) -> Any:
        """Compile the durable state graph around a supplied PostgreSQL checkpointer."""
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError:
            raise GraphEngineDependencyError(
                "langgraph is required to compile the TalentForge graph."
            ) from None

        workflow = StateGraph(TalentForgeGraphState)
        workflow.add_node("check_cache", self.check_cache_node)
        workflow.add_node("call_mcp_tool", self.call_mcp_tool_node)
        workflow.add_node("analyze_root_cause", self.analyze_root_cause_node)
        workflow.add_node("draft_email", self.draft_email_node)
        workflow.add_node("escalate_to_human", self.escalate_to_human_node)

        workflow.add_edge(START, "check_cache")
        workflow.add_conditional_edges(
            "check_cache",
            self._route_after_cache,
            {"complete": END, "retrieve": "call_mcp_tool"},
        )
        workflow.add_conditional_edges(
            "call_mcp_tool",
            self._route_after_tool_call,
            {
                "retry": "call_mcp_tool",
                "escalate": "escalate_to_human",
                "analyze": "analyze_root_cause",
            },
        )
        workflow.add_edge("analyze_root_cause", "draft_email")
        workflow.add_edge("draft_email", END)
        workflow.add_edge("escalate_to_human", END)
        return workflow.compile(checkpointer=checkpointer)

    @staticmethod
    def _route_after_cache(
        state: TalentForgeGraphState,
    ) -> Literal["complete", "retrieve"]:
        if state["semantic_cache_hit"] or state["final_draft"]:
            return "complete"
        return "retrieve"

    @staticmethod
    def _route_after_tool_call(
        state: TalentForgeGraphState,
    ) -> Literal["retry", "escalate", "analyze"]:
        if not state["tool_errors"]:
            return "analyze"
        retry_count = max(0, _coerce_int(state["retry_count"]))
        retry_limit = _bounded_retry_limit(state["max_retries"])
        if retry_count < retry_limit:
            return "retry"
        return "escalate"

    async def _customer_in_cooldown(self, session: Any, customer_id: str) -> bool:
        cutoff = datetime.now(timezone.utc) - timedelta(
            hours=self.settings.cooldown_hours
        )
        statement = (
            select(OutreachCampaign.id)
            .where(OutreachCampaign.customer_id == customer_id)
            .where(OutreachCampaign.created_at >= cutoff)
            .limit(1)
        )
        return (await session.execute(statement)).scalar_one_or_none() is not None

    async def _stage_pending_review_campaign(
        self, state: TalentForgeGraphState, draft: str
    ) -> None:
        incident_signature = _incident_signature(state)
        try:
            async with self._cache_session_factory() as session:
                session.add(
                    OutreachCampaign(
                        customer_id=state["customer_id"],
                        incident_signature_hash=incident_signature,
                        status=CampaignStatus.PENDING_REVIEW,
                        draft_content=draft,
                        generated_by_agent="talentforge_langgraph",
                    )
                )
                await session.flush()
        except IntegrityError:
            # The schema's customer/signature uniqueness protects resumed graphs.
            return


def checkpoint_database_url(database_url: str | None = None) -> str:
    """Return a psycopg-compatible PostgreSQL URL without logging credentials."""
    raw_url = (
        database_url
        or os.getenv("LANGGRAPH_CHECKPOINT_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or ""
    ).strip()
    if not raw_url:
        raise GraphEngineConfigurationError(
            "LANGGRAPH_CHECKPOINT_DATABASE_URL or DATABASE_URL must be configured."
        )

    parsed = urlsplit(raw_url)
    if parsed.scheme == "postgresql+asyncpg":
        return urlunsplit(("postgresql", parsed.netloc, parsed.path, parsed.query, ""))
    if parsed.scheme == "postgres":
        return urlunsplit(("postgresql", parsed.netloc, parsed.path, parsed.query, ""))
    if parsed.scheme == "postgresql":
        return raw_url
    raise GraphEngineConfigurationError(
        "The LangGraph checkpoint database URL must use a PostgreSQL scheme."
    )


def _effective_checkpointer_mode() -> Literal["memory", "postgres"]:
    """Use a local-only saver when Windows runs Psycopg on a Proactor loop."""
    configured = os.getenv(CHECKPOINTER_MODE_ENV, "auto").strip().lower()
    if configured == "memory":
        return "memory"
    if configured == "postgres":
        return "postgres"
    if configured != "auto":
        raise GraphEngineConfigurationError(
            f"{CHECKPOINTER_MODE_ENV} must be auto, memory, or postgres."
        )

    loop_name = type(asyncio.get_running_loop()).__name__.lower()
    return "memory" if os.name == "nt" and "proactor" in loop_name else "postgres"


@asynccontextmanager
async def postgres_checkpointer(
    database_url: str | None = None,
) -> AsyncIterator[Any]:
    """Keep a PostgreSQL LangGraph checkpointer alive for a graph's lifetime."""
    if _effective_checkpointer_mode() == "memory":
        try:
            from langgraph.checkpoint.memory import MemorySaver
        except ImportError:
            raise GraphEngineDependencyError(
                "langgraph checkpoint memory support is required for local Windows runs."
            ) from None
        logger.warning(
            "Using an in-memory LangGraph checkpointer because Psycopg async is "
            "incompatible with the active Windows Proactor event loop."
        )
        yield MemorySaver()
        return

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    except ImportError:
        raise GraphEngineDependencyError(
            "langgraph-checkpoint-postgres is required for durable graph state."
        ) from None

    async with AsyncPostgresSaver.from_conn_string(
        checkpoint_database_url(database_url)
    ) as checkpointer:
        await checkpointer.setup()
        yield checkpointer


@asynccontextmanager
async def persistent_talentforge_graph(
    *,
    engine: TalentForgeGraphEngine | None = None,
    database_url: str | None = None,
) -> AsyncIterator[Any]:
    """Yield a compiled graph whose PostgreSQL checkpointer stays connected."""
    async with postgres_checkpointer(database_url) as checkpointer:
        yield (engine or TalentForgeGraphEngine()).compile(checkpointer)


def _tool_routing_messages(state: TalentForgeGraphState) -> list[tuple[str, str]]:
    return [
        (
            "system",
            "You are the Data Routing Agent. Decide which read-only MCP database "
            "tools to call for this customer churn alert, selecting the minimum "
            "effective set to reduce latency and cost. Use the supplied customer_id "
            "exactly as provided. Never hallucinate customer data and never request "
            "write or mutating operations.",
        ),
        (
            "human",
            "customer_id="
            f"{state['customer_id']}\nalert_context={_bounded_json(state['alert_context'], 8_000)}",
        ),
    ]


def _root_cause_messages(state: TalentForgeGraphState) -> list[tuple[str, str]]:
    return [
        (
            "system",
            "You are the Root-Cause Intelligence Agent. Perform rigorous diagnostic "
            "analysis over the supplied telemetry alert and MCP-retrieved CRM history. "
            "Return a structured report with verified evidence sourced only from the "
            "records, clearly labeled inferred hypotheses, urgency level "
            "(Critical/High/Medium/Low), risk category (Churn/Disengagement/"
            "Technical/Billing/Relationship), and recommended next actions. Think "
            "step by step internally, but do not expose chain-of-thought. Do not claim "
            "certainty when retrieved telemetry is incomplete.",
        ),
        (
            "human",
            "customer_id="
            f"{state['customer_id']}\nalert_context={_bounded_json(state['alert_context'], 8_000)}"
            f"\nhistorical_records={state['analysis_output']}",
        ),
    ]


def _outreach_drafting_messages(state: TalentForgeGraphState) -> list[tuple[str, str]]:
    return [
        (
            "system",
            "You are the Customer Success Outreach Agent. Draft a premium, proactive, "
            "professional outreach email using the analysis_output and alert_context "
            "to personalize the message. Acknowledge the customer's friction without "
            "legal admissions of fault. Include a relevant subject line, warm opening "
            "addressing the issue, product value alignment, and one low-friction CTA. "
            "Do not add unsupported promises, compensation, or deadlines. Mark this "
            "as a draft for human review, never a message sent directly.",
        ),
        (
            "human",
            "customer_id="
            f"{state['customer_id']}\nalert_context={_bounded_json(state['alert_context'], 8_000)}"
            f"\nroot_cause_analysis={state['analysis_output']}",
        ),
    ]


def _formatting_messages(frontier_draft: str) -> list[tuple[str, str]]:
    return [
        (
            "system",
            "You are the Polish & Formatting Agent. Format the frontier-drafted email "
            "candidate into a clean, production-ready email string. Preserve every "
            "fact, nuance, context, and strategic intent. Do not add or remove claims, "
            "offers, commitments, dates, or context. Return exactly: "
            "Subject: <subject line>\n\n<email body>",
        ),
        ("human", frontier_draft),
    ]


async def score_customer_risk(customer_id: UUID | str, session: Any) -> dict[str, Any]:
    """Use Luna to produce an evidence-bound JSON customer risk assessment."""
    customer_uuid = UUID(str(customer_id))
    customer = await session.get(CustomerProfile, customer_uuid)
    result = await session.execute(
        select(InteractionHistory)
        .where(InteractionHistory.customer_id == customer_uuid)
        .order_by(InteractionHistory.timestamp.desc())
        .limit(50)
    )
    interactions = list(result.scalars().all())

    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        raise GraphEngineDependencyError(
            "langchain-openai is required to score customer risk."
        ) from None

    model = ChatOpenAI(
        model=_environment_value("TALENTFORGE_ROUTING_MODEL", DEFAULT_FAST_MODEL),
        max_retries=0,
    )
    scorer = model.with_structured_output(RiskAssessment)
    response = await scorer.ainvoke(
        [
            (
                "system",
                "You are TalentForge's Proactive Risk Scoring Agent running on "
                "GPT-5.6 Luna. Base the assessment only on "
                "the supplied customer profile and interaction history. Do not "
                "invent facts.",
            ),
            (
                "human",
                _bounded_json(
                    {
                        "customer_id": str(customer_uuid),
                        "customer": customer.model_dump() if customer else None,
                        "interactions": [
                            interaction.model_dump() for interaction in interactions
                        ],
                    },
                    DEFAULT_MAX_TOOL_RESULT_CHARS,
                ),
            ),
        ]
    )

    return response.model_dump()


def _company_agent_model() -> Any:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        raise GraphEngineDependencyError(
            "langchain-openai is required to run TalentForge company agents."
        ) from None
    return ChatOpenAI(
        model=_environment_value("TALENTFORGE_ROUTING_MODEL", DEFAULT_FAST_MODEL),
        max_retries=0,
    )


async def _company_customers(
    session: Any,
    company_id: UUID,
    config: dict[str, Any],
) -> list[CustomerProfile]:
    statement = select(CustomerProfile).where(CustomerProfile.company_id == company_id)
    raw_ids = config.get("customer_ids", [])
    if raw_ids:
        customer_ids = [UUID(str(customer_id)) for customer_id in raw_ids]
        statement = statement.where(CustomerProfile.id.in_(customer_ids))
    limit = min(max(int(config.get("limit", 25)), 1), 50)
    result = await session.execute(statement.order_by(CustomerProfile.updated_at.desc()).limit(limit))
    return list(result.scalars().all())


async def _churn_risk_node(
    state: CompanyAgentState,
    session: Any,
) -> dict[str, Any]:
    company_id = UUID(state["company_id"])
    customers = await _company_customers(session, company_id, state["config"])
    model = _company_agent_model().with_structured_output(ChurnRiskScoringResult)
    response = await model.ainvoke(
        [
            (
                "system",
                "You are the Churn Risk Scorer. Return scores only for supplied "
                "customers, using evidence in their profiles. Keep scores from 0 to 100.",
            ),
            ("human", _bounded_json([customer.model_dump() for customer in customers], 24_000)),
        ]
    )
    customer_by_id = {customer.id: customer for customer in customers}
    updated = []
    for score in response.scores:
        customer = customer_by_id.get(score.customer_id)
        if customer is None:
            continue
        customer.health_score = score.health_score
        session.add(CustomerHealthHistory(
            customer_id=customer.id,
            health_score=score.health_score,
            reason=score.reason,
        ))
        updated.append(score.model_dump(mode="json"))
    await session.flush()
    return {"output": {"updated_customers": updated}}


async def _root_cause_node(
    state: CompanyAgentState,
    session: Any,
) -> dict[str, Any]:
    company_id = UUID(state["company_id"])
    customers = await _company_customers(session, company_id, state["config"])
    customer_ids = [customer.id for customer in customers]
    interactions = []
    embeddings = []
    mcp_results: list[dict[str, Any]] = []
    if customer_ids:
        interaction_result = await session.execute(
            select(InteractionHistory)
            .where(InteractionHistory.customer_id.in_(customer_ids))
            .order_by(InteractionHistory.timestamp.desc())
            .limit(100)
        )
        interactions = [item.model_dump() for item in interaction_result.scalars().all()]
        from talentforge.db.models import CustomerEmbedding

        embedding_result = await session.execute(
            select(CustomerEmbedding.content)
            .where(CustomerEmbedding.customer_id.in_(customer_ids))
            .limit(20)
        )
        embeddings = [content for content in embedding_result.scalars().all()]
    if state["config"].get("use_mcp", True) and customer_ids:
        try:
            from talentforge.mcp_client import postgres_mcp_tool_session

            async with postgres_mcp_tool_session() as tools:
                router = _company_agent_model().bind_tools(tools)
                tool_response = await router.ainvoke(
                    [
                        ("system", "Select the minimum read-only tools needed for these customer IDs."),
                        ("human", _bounded_json({"customer_ids": [str(customer_id) for customer_id in customer_ids]}, 4_000)),
                    ]
                )
                tool_by_name = {tool.name: tool for tool in tools}
                for call in list(getattr(tool_response, "tool_calls", []) or [])[:2]:
                    tool = tool_by_name.get(str(call.get("name", "")))
                    if tool is not None:
                        mcp_results.append({"tool": tool.name, "result": await tool.ainvoke(call.get("args", {}))})
        except Exception:
            mcp_results = []

    model = _company_agent_model().with_structured_output(RootCauseReport)
    response = await model.ainvoke(
        [
            (
                "system",
                "You are the Root Cause Analyst. Produce evidence-bound causes and "
                "actions using only supplied CRM history and semantic context.",
            ),
            (
                "human",
                _bounded_json(
                    {"customers": [customer.model_dump() for customer in customers], "interactions": interactions, "semantic_context": embeddings, "mcp_history": mcp_results},
                    32_000,
                ),
            ),
        ]
    )
    return {"output": response.model_dump()}


async def _outreach_draft_node(
    state: CompanyAgentState,
    session: Any,
) -> dict[str, Any]:
    company_id = UUID(state["company_id"])
    customers = await _company_customers(session, company_id, state["config"])
    goal = str(state["config"].get("goal", "re-engage"))
    model = _company_agent_model().with_structured_output(OutreachDraftResult)
    response = await model.ainvoke(
        [
            (
                "system",
                "You are the Outreach Drafter. Create a human-review campaign draft. "
                "Never promise compensation, dates, or automatic sending.",
            ),
            ("human", _bounded_json({"goal": goal, "customers": [customer.model_dump() for customer in customers]}, 24_000)),
        ]
    )
    campaign = Campaign(
        company_id=company_id,
        name=response.campaign_name,
        status="pending_review",
        target_segment={"customer_ids": [str(customer_id) for customer_id in response.target_customer_ids]},
        message_template=f"Subject: {response.subject}\n\n{response.message_template}",
    )
    session.add(campaign)
    await session.flush()
    return {"output": {"campaign_id": str(campaign.id), **response.model_dump(mode="json")}}


async def _health_score_update_node(
    state: CompanyAgentState,
    session: Any,
) -> dict[str, Any]:
    company_id = UUID(state["company_id"])
    customers = await _company_customers(session, company_id, state["config"])
    updates = []
    for customer in customers:
        interaction_result = await session.execute(
            select(func.count(InteractionHistory.id)).where(InteractionHistory.customer_id == customer.id)
        )
        interaction_count = int(interaction_result.scalar_one())
        score = min(100.0, max(0.0, 50.0 + min(interaction_count, 20) * 2.5))
        customer.health_score = score
        session.add(CustomerHealthHistory(
            customer_id=customer.id,
            health_score=score,
            reason="Health score recalculated from CRM activity volume.",
        ))
        updates.append({"customer_id": str(customer.id), "health_score": score})
    await session.flush()
    return {"output": {"updated_customers": updates}}


def _compile_company_agent_graph(node: Any, checkpointer: Any | None = None) -> Any:
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        raise GraphEngineDependencyError("langgraph is required to run company agents.") from None

    async def execute(state: CompanyAgentState) -> dict[str, Any]:
        """Await graph-node factories passed as concise state lambdas."""
        return await node(state)

    workflow = StateGraph(CompanyAgentState)
    workflow.add_node("execute", execute)
    workflow.add_edge(START, "execute")
    workflow.add_edge("execute", END)
    return workflow.compile(checkpointer=checkpointer)


def build_churn_risk_scorer_graph(session: Any, checkpointer: Any | None = None) -> Any:
    return _compile_company_agent_graph(lambda state: _churn_risk_node(state, session), checkpointer)


def build_root_cause_analyst_graph(session: Any, checkpointer: Any | None = None) -> Any:
    return _compile_company_agent_graph(lambda state: _root_cause_node(state, session), checkpointer)


def build_outreach_drafter_graph(session: Any, checkpointer: Any | None = None) -> Any:
    return _compile_company_agent_graph(lambda state: _outreach_draft_node(state, session), checkpointer)


def build_health_score_updater_graph(session: Any, checkpointer: Any | None = None) -> Any:
    return _compile_company_agent_graph(lambda state: _health_score_update_node(state, session), checkpointer)


async def run_company_agent(
    agent_type: str,
    company_id: UUID,
    config: dict[str, Any],
    session: Any,
    checkpointer: Any | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    graphs = {
        "churn_analysis": build_churn_risk_scorer_graph(session, checkpointer),
        "root_cause": build_root_cause_analyst_graph(session, checkpointer),
        "outreach_draft": build_outreach_drafter_graph(session, checkpointer),
        "health_scoring": build_health_score_updater_graph(session, checkpointer),
    }
    graph = graphs.get(agent_type)
    if graph is None:
        raise ValueError("Unsupported agent type.")
    result = await graph.ainvoke(
        {"company_id": str(company_id), "config": config, "output": {}},
        config={"configurable": {"thread_id": thread_id or str(company_id)}},
    )
    return dict(result["output"])


def _alert_embedding(alert_context: dict[str, Any]) -> list[float] | None:
    candidate = alert_context.get("semantic_embedding", alert_context.get("embedding"))
    if not isinstance(candidate, list) or not all(
        isinstance(value, (int, float)) for value in candidate
    ):
        return None
    return [float(value) for value in candidate]


def _incident_signature(state: TalentForgeGraphState) -> str:
    source = str(
        state["alert_context"].get("error_signature")
        or state["alert_context"].get("event_id")
        or _bounded_json(state["alert_context"], 8_000)
    )
    material = f"{state['customer_id']}:{source}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _human_review_draft() -> str:
    return (
        "Subject: Customer follow-up requires review\n\n"
        "A customer-success team member should review the incident context and "
        "prepare a personalized response before any outreach is sent."
    )


def _cooldown_notice() -> str:
    return (
        "No outreach draft was created because this customer is within the "
        "24-hour communication cooldown window."
    )


def _message_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content.strip()
    return _bounded_json(content, DEFAULT_MAX_TOOL_RESULT_CHARS)


def _bounded_json(value: Any, limit: int) -> str:
    try:
        rendered = json.dumps(value, default=str, ensure_ascii=True, sort_keys=True)
    except (TypeError, ValueError):
        rendered = str(value)
    return rendered[:limit]


def _environment_value(name: str, default: str) -> str:
    return os.getenv(name, default).strip() or default


def _positive_float(name: str, default: float) -> float:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = float(raw_value)
    except ValueError:
        raise GraphEngineConfigurationError(f"{name} must be a positive number.") from None
    if value <= 0:
        raise GraphEngineConfigurationError(f"{name} must be a positive number.")
    return value


def _positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        raise GraphEngineConfigurationError(f"{name} must be a positive integer.") from None
    if value <= 0:
        raise GraphEngineConfigurationError(f"{name} must be a positive integer.")
    return value


def _bounded_retry_limit(value: int) -> int:
    return min(MAX_TOOL_RETRIES, max(0, _coerce_int(value)))


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
