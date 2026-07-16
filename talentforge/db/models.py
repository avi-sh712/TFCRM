"""SQLModel table definitions for TalentForge."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, Relationship, SQLModel


def enum_values(enum_cls: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_cls]


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp for client-side defaults."""
    return datetime.now(timezone.utc)


class UserRole(StrEnum):
    ADMIN = "admin"
    COMPANY = "company"
    CSM = "csm"
    VIEWER = "viewer"


class CampaignStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    SENT = "sent"
    REJECTED = "rejected"


class DealStage(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    PROPOSAL = "proposal"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


class TimestampMixin(SQLModel):
    """Common UUID primary key pattern used by TalentForge tables."""

    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        sa_type=PG_UUID(as_uuid=True),
        nullable=False,
    )


class User(TimestampMixin, table=True):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("username", name="uq_users_username"),
        Index("ix_users_email", "email"),
    )

    email: str = Field(max_length=320, nullable=False)
    username: str | None = Field(default=None, max_length=32, nullable=True)
    hashed_password: str = Field(max_length=255, nullable=False)
    role: UserRole = Field(
        default=UserRole.COMPANY,
        sa_column=Column(
            Enum(
                UserRole,
                name="user_role",
                native_enum=False,
                validate_strings=True,
                values_callable=enum_values,
            ),
            nullable=False,
            server_default=UserRole.COMPANY.value,
        ),
    )
    company_name: str | None = Field(default=None, max_length=255)
    plan: str = Field(
        default="free",
        max_length=50,
        sa_column=Column(String(50), nullable=False, server_default="free"),
    )
    suspended: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )

    reviewed_campaigns: list["OutreachCampaign"] = Relationship(
        back_populates="reviewer",
        sa_relationship_kwargs={"foreign_keys": "[OutreachCampaign.reviewed_by]"},
    )


class CustomerProfile(TimestampMixin, table=True):
    __tablename__ = "customer_profiles"
    __table_args__ = (
        Index("ix_customer_profiles_company_name", "company_name"),
        Index("ix_customer_profiles_company_id", "company_id"),
        Index("ix_customer_profiles_company_status", "company_id", "status"),
    )

    company_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    company_name: str = Field(max_length=255, nullable=False)
    contact_email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=32)
    status: str = Field(
        default="healthy",
        max_length=32,
        sa_column=Column(
            String(32),
            nullable=False,
            server_default="healthy",
        ),
    )
    health_score: float = Field(default=0.0, nullable=False)
    contract_value: float = Field(default=0.0, nullable=False)
    mrr: float = Field(
        default=0.0,
        sa_column=Column(Float, nullable=False, server_default="0"),
    )
    lifetime_value: float = Field(
        default=0.0,
        sa_column=Column(Float, nullable=False, server_default="0"),
    )
    purchase_count: int = Field(default=0, nullable=False)
    last_purchase_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_contact: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    tags: list[str] | None = Field(
        default=None,
        sa_column=Column(ARRAY(String), nullable=True),
    )
    notes: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )

    interactions: list["InteractionHistory"] = Relationship(back_populates="customer")
    campaigns: list["OutreachCampaign"] = Relationship(back_populates="customer")


class InteractionHistory(TimestampMixin, table=True):
    __tablename__ = "interaction_history"
    __table_args__ = (
        Index("ix_interaction_history_customer_id", "customer_id"),
        Index("ix_interaction_history_timestamp", "timestamp"),
        Index(
            "ix_interaction_history_semantic_signature_hnsw",
            "semantic_signature",
            postgresql_using="hnsw",
            postgresql_ops={"semantic_signature": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
        ),
    )

    customer_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("customer_profiles.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    event_type: str = Field(max_length=100, nullable=False)
    raw_payload: str = Field(sa_column=Column(Text, nullable=False))
    semantic_signature: list[float] | None = Field(
        default=None,
        sa_column=Column(Vector(1536), nullable=True),
    )
    timestamp: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )

    customer: CustomerProfile = Relationship(back_populates="interactions")


class OutreachCampaign(TimestampMixin, table=True):
    __tablename__ = "outreach_campaigns"
    __table_args__ = (
        Index("ix_outreach_campaigns_customer_id", "customer_id"),
        Index("ix_outreach_campaigns_incident_signature_hash", "incident_signature_hash"),
        UniqueConstraint(
            "customer_id",
            "incident_signature_hash",
            name="uq_outreach_campaigns_customer_incident_hash",
        ),
    )

    customer_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("customer_profiles.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    incident_signature_hash: str = Field(max_length=128, nullable=False)
    status: CampaignStatus = Field(
        default=CampaignStatus.PENDING_REVIEW,
        sa_column=Column(
            Enum(
                CampaignStatus,
                name="campaign_status",
                native_enum=False,
                validate_strings=True,
                values_callable=enum_values,
            ),
            nullable=False,
            server_default=CampaignStatus.PENDING_REVIEW.value,
        ),
    )
    draft_content: str = Field(sa_column=Column(Text, nullable=False))
    generated_by_agent: str = Field(max_length=100, nullable=False)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )
    reviewed_by: UUID | None = Field(
        default=None,
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    customer: CustomerProfile = Relationship(back_populates="campaigns")
    reviewer: User | None = Relationship(
        back_populates="reviewed_campaigns",
        sa_relationship_kwargs={"foreign_keys": "[OutreachCampaign.reviewed_by]"},
    )


class AgentAuditLog(TimestampMixin, table=True):
    __tablename__ = "agent_audit_logs"
    __table_args__ = (
        Index("ix_agent_audit_logs_session_id", "session_id"),
        Index("ix_agent_audit_logs_timestamp", "timestamp"),
    )

    session_id: str = Field(max_length=128, nullable=False)
    node_name: str = Field(max_length=128, nullable=False)
    action_taken: str = Field(sa_column=Column(Text, nullable=False))
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    timestamp: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )


class DataSource(TimestampMixin, table=True):
    __tablename__ = "data_sources"
    __table_args__ = (
        Index("ix_data_sources_company_id", "company_id"),
        Index("ix_data_sources_company_status", "company_id", "status"),
    )

    company_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    type: str = Field(max_length=64, nullable=False)
    name: str = Field(max_length=255, nullable=False)
    status: str = Field(default="connected", max_length=32, nullable=False)
    last_sync: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    config: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )


class ImportJob(TimestampMixin, table=True):
    __tablename__ = "import_jobs"
    __table_args__ = (
        Index("ix_import_jobs_company_created_at", "company_id", "created_at"),
        Index("ix_import_jobs_company_status", "company_id", "status"),
    )

    company_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    filename: str = Field(max_length=255, nullable=False)
    raw_csv: str = Field(sa_column=Column(Text, nullable=False))
    status: str = Field(default="queued", max_length=32, nullable=False)
    rows_imported: int = Field(default=0, nullable=False)
    rows_skipped: int = Field(default=0, nullable=False)
    error_message: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    completed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class AgentRun(TimestampMixin, table=True):
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_company_created_at", "company_id", "created_at"),
        Index("ix_agent_runs_company_status", "company_id", "status"),
    )

    company_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    type: str = Field(max_length=64, nullable=False)
    status: str = Field(default="queued", max_length=32, nullable=False)
    input: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    output: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    credits_used: int = Field(default=0, nullable=False)
    started_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    completed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )


class Campaign(TimestampMixin, table=True):
    __tablename__ = "campaigns"
    __table_args__ = (
        Index("ix_campaigns_company_created_at", "company_id", "created_at"),
        Index("ix_campaigns_company_status", "company_id", "status"),
    )

    company_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    name: str = Field(max_length=255, nullable=False)
    status: str = Field(default="draft", max_length=32, nullable=False)
    target_segment: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    message_template: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    scheduled_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    sent_count: int = Field(default=0, nullable=False)
    open_rate: float | None = Field(default=None, nullable=True)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )


class Deal(TimestampMixin, table=True):
    __tablename__ = "deals"
    __table_args__ = (
        Index("ix_deals_company_stage", "company_id", "stage"),
        Index("ix_deals_customer_id", "customer_id"),
    )

    company_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    customer_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("customer_profiles.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    name: str = Field(max_length=255, nullable=False)
    value: float = Field(default=0, sa_column=Column(Float, nullable=False, server_default="0"))
    stage: DealStage = Field(
        default=DealStage.NEW,
        sa_column=Column(
            Enum(
                DealStage,
                name="deal_stage",
                native_enum=False,
                validate_strings=True,
                values_callable=enum_values,
            ),
            nullable=False,
            server_default=DealStage.NEW.value,
        ),
    )
    notes: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    expected_close_date: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )


class CustomerEmbedding(TimestampMixin, table=True):
    __tablename__ = "customer_embeddings"
    __table_args__ = (Index("ix_customer_embeddings_customer_id", "customer_id"),)

    customer_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("customer_profiles.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    content: str = Field(sa_column=Column(Text, nullable=False))
    embedding: list[float] = Field(sa_column=Column(Vector(1536), nullable=False))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )


class CustomerHealthHistory(TimestampMixin, table=True):
    __tablename__ = "customer_health_history"
    __table_args__ = (
        Index("ix_customer_health_history_customer_recorded_at", "customer_id", "recorded_at"),
    )

    customer_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("customer_profiles.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    health_score: float = Field(nullable=False)
    reason: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    recorded_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )


class WebhookEvent(TimestampMixin, table=True):
    __tablename__ = "webhook_events"
    __table_args__ = (
        Index("ix_webhook_events_company_created_at", "company_id", "created_at"),
        Index("ix_webhook_events_customer_id", "customer_id"),
    )

    company_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    customer_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("customer_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    event_type: str = Field(max_length=100, nullable=False)
    payload: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )


class TelemetryIngestionDeduplication(TimestampMixin, table=True):
    __tablename__ = "telemetry_ingestion_deduplication"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_telemetry_ingestion_deduplication_idempotency_key",
        ),
        Index(
            "ix_telemetry_ingestion_deduplication_customer_hour",
            "customer_id",
            "hour_bucket",
        ),
        Index(
            "ix_telemetry_ingestion_deduplication_created_at",
            "created_at",
        ),
    )

    idempotency_key: str = Field(max_length=32, nullable=False)
    customer_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("customer_profiles.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    error_signature: str = Field(max_length=512, nullable=False)
    hour_bucket: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )
