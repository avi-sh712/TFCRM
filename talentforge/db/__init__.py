"""Database exports for TalentForge."""

from talentforge.db.database import (
    APP_READONLY_ROLE_SQL,
    PGVECTOR_EXTENSION_SQL,
    async_engine,
    close_database,
    create_all_tables,
    get_db_session,
    init_database,
    session_factory,
)
from talentforge.db.cache_service import check_semantic_cache, store_semantic_cache
from talentforge.db.models import (
    AgentAuditLog,
    CampaignStatus,
    CustomerProfile,
    InteractionHistory,
    OutreachCampaign,
    TelemetryIngestionDeduplication,
    User,
    UserRole,
)

__all__ = [
    "APP_READONLY_ROLE_SQL",
    "PGVECTOR_EXTENSION_SQL",
    "AgentAuditLog",
    "CampaignStatus",
    "CustomerProfile",
    "InteractionHistory",
    "OutreachCampaign",
    "TelemetryIngestionDeduplication",
    "User",
    "UserRole",
    "async_engine",
    "close_database",
    "create_all_tables",
    "get_db_session",
    "init_database",
    "session_factory",
    "check_semantic_cache",
    "store_semantic_cache",
]
