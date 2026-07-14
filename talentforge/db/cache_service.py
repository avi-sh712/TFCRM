"""Semantic incident-resolution cache backed by pgvector."""

from __future__ import annotations

from typing import Final, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from talentforge.db.models import InteractionHistory


EMBEDDING_DIMENSIONS: Final = 1536


def _validate_embedding(embedding: list[float]) -> None:
    """Reject malformed vectors before they reach PostgreSQL."""
    if len(embedding) != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"Expected a {EMBEDDING_DIMENSIONS}-dimension embedding, "
            f"received {len(embedding)} dimensions."
        )


def _cosine_distance_limit(threshold: float) -> float:
    """Convert cosine similarity to pgvector's cosine-distance threshold."""
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0.0 and 1.0 inclusive.")
    return 1.0 - threshold


async def check_semantic_cache(
    session: AsyncSession,
    alert_embedding: list[float],
    threshold: float = 0.95,
) -> Optional[str]:
    """
    Return the closest validated incident payload when it meets the similarity bar.

    pgvector's cosine distance is ``1 - cosine_similarity``. A 0.95 similarity
    threshold therefore accepts only a nearest neighbor at distance <= 0.05.
    """
    _validate_embedding(alert_embedding)
    distance_limit = _cosine_distance_limit(threshold)

    cosine_distance = InteractionHistory.semantic_signature.cosine_distance(
        alert_embedding
    ).label("cosine_distance")
    statement = (
        select(InteractionHistory.raw_payload, cosine_distance)
        .where(InteractionHistory.semantic_signature.is_not(None))
        .order_by(cosine_distance)
        .limit(1)
    )

    result = await session.execute(statement)
    match = result.first()
    if match is None:
        return None

    raw_payload, distance = match
    if float(distance) <= distance_limit:
        return raw_payload
    return None


async def store_semantic_cache(
    session: AsyncSession,
    customer_id: UUID,
    event_type: str,
    raw_payload: str,
    embedding: list[float],
) -> None:
    """Stage a validated incident playbook for semantic-cache retrieval."""
    _validate_embedding(embedding)

    session.add(
        InteractionHistory(
            customer_id=customer_id,
            event_type=event_type,
            raw_payload=raw_payload,
            semantic_signature=embedding,
        )
    )
    await session.flush()
