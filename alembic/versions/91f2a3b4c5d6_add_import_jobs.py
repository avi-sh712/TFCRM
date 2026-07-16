"""add persistent csv import jobs

Revision ID: 91f2a3b4c5d6
Revises: 749c3c4e5d6f
"""

from alembic import op
import sqlalchemy as sa


revision = "91f2a3b4c5d6"
down_revision = "749c3c4e5d6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("import_jobs"):
        op.create_table(
            "import_jobs",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("raw_csv", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
            sa.Column("rows_imported", sa.Integer(), server_default="0", nullable=False),
            sa.Column("rows_skipped", sa.Integer(), server_default="0", nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    index_names = {index["name"] for index in inspector.get_indexes("import_jobs")}
    if "ix_import_jobs_company_created_at" not in index_names:
        op.create_index("ix_import_jobs_company_created_at", "import_jobs", ["company_id", "created_at"], unique=False)
    if "ix_import_jobs_company_status" not in index_names:
        op.create_index("ix_import_jobs_company_status", "import_jobs", ["company_id", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_import_jobs_company_status", table_name="import_jobs")
    op.drop_index("ix_import_jobs_company_created_at", table_name="import_jobs")
    op.drop_table("import_jobs")
