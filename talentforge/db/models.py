"""SQLModel table definitions for TalentForge."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
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
    CSM = "csm"
    VIEWER = "viewer"


class CampaignStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    SENT = "sent"
    REJECTED = "rejected"


class TimestampMixin(SQLModel):
    """Common UUID primary key pattern used by TalentForge tables."""

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True, nullable=False),
    )


class User(TimestampMixin, table=True):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_email", "email"),
    )

    email: str = Field(max_length=320, nullable=False)
    hashed_password: str = Field(max_length=255, nullable=False)
    role: UserRole = Field(
        default=UserRole.VIEWER,
        sa_column=Column(
            Enum(
                UserRole,
                name="user_role",
                native_enum=False,
                validate_strings=True,
                values_callable=enum_values,
            ),
            nullable=False,
            server_default=UserRole.VIEWER.value,
        ),
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
    __table_args__ = (Index("ix_customer_profiles_company_name", "company_name"),)

    company_name: str = Field(max_length=255, nullable=False)
    health_score: float = Field(default=0.0, nullable=False)
    contract_value: float = Field(default=0.0, nullable=False)
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
