"""add workspace memberships for company teams

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
"""

from alembic import op
import sqlalchemy as sa


revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "workspace_id" not in columns:
        op.add_column("users", sa.Column("workspace_id", sa.UUID(), nullable=True))
        op.execute("UPDATE users SET workspace_id = id WHERE workspace_id IS NULL")
    foreign_keys = inspector.get_foreign_keys("users")
    if not any(foreign_key["constrained_columns"] == ["workspace_id"] for foreign_key in foreign_keys):
        op.create_foreign_key("fk_users_workspace_id", "users", "users", ["workspace_id"], ["id"], ondelete="CASCADE")
    indexes = {index["name"] for index in inspector.get_indexes("users")}
    if "ix_users_workspace_id" not in indexes:
        op.create_index("ix_users_workspace_id", "users", ["workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_workspace_id", table_name="users")
    op.drop_constraint("fk_users_workspace_id", "users", type_="foreignkey")
    op.drop_column("users", "workspace_id")
