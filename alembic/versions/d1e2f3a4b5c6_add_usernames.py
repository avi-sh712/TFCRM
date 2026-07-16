"""add usernames for dual-identifier login

Revision ID: d1e2f3a4b5c6
Revises: c6d7e8f9a0b1
"""

from alembic import op
import sqlalchemy as sa


revision = "d1e2f3a4b5c6"
down_revision = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "username" not in columns:
        op.add_column("users", sa.Column("username", sa.String(length=32), nullable=True))
    constraint_names = {constraint["name"] for constraint in inspector.get_unique_constraints("users")}
    if "uq_users_username" not in constraint_names:
        op.create_unique_constraint("uq_users_username", "users", ["username"])


def downgrade() -> None:
    op.drop_constraint("uq_users_username", "users", type_="unique")
    op.drop_column("users", "username")
