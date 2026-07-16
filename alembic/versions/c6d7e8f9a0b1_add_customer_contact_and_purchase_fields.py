"""add customer contact and purchase fields

Revision ID: c6d7e8f9a0b1
Revises: 91f2a3b4c5d6
"""

from alembic import op
import sqlalchemy as sa


revision = "c6d7e8f9a0b1"
down_revision = "91f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("customer_profiles")}
    if "phone" not in columns:
        op.add_column("customer_profiles", sa.Column("phone", sa.String(length=32), nullable=True))
    if "lifetime_value" not in columns:
        op.add_column("customer_profiles", sa.Column("lifetime_value", sa.Float(), server_default="0", nullable=False))
    if "purchase_count" not in columns:
        op.add_column("customer_profiles", sa.Column("purchase_count", sa.Integer(), server_default="0", nullable=False))
    if "last_purchase_at" not in columns:
        op.add_column("customer_profiles", sa.Column("last_purchase_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("customer_profiles", "last_purchase_at")
    op.drop_column("customer_profiles", "purchase_count")
    op.drop_column("customer_profiles", "lifetime_value")
    op.drop_column("customer_profiles", "phone")
