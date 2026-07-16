"""add deal pipeline

Revision ID: 749c3c4e5d6f
Revises: 2d16e2a3527b
"""

from alembic import op
import sqlalchemy as sa


revision = "749c3c4e5d6f"
down_revision = "2d16e2a3527b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("deals"):
        op.create_table(
            "deals",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("customer_id", sa.UUID(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("value", sa.Float(), server_default="0", nullable=False),
            sa.Column("stage", sa.String(length=32), server_default="new", nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("expected_close_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["customer_id"], ["customer_profiles.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    index_names = {index["name"] for index in inspector.get_indexes("deals")}
    if "ix_deals_company_stage" not in index_names:
        op.create_index("ix_deals_company_stage", "deals", ["company_id", "stage"], unique=False)
    if "ix_deals_customer_id" not in index_names:
        op.create_index("ix_deals_customer_id", "deals", ["customer_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_deals_customer_id", table_name="deals")
    op.drop_index("ix_deals_company_stage", table_name="deals")
    op.drop_table("deals")
