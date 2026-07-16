"""add crm platform models

Revision ID: 2d16e2a3527b
Revises:
Create Date: 2026-07-16 15:00:40.595521
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
import sqlmodel

import talentforge.db.models  # noqa: F401


revision = '2d16e2a3527b'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table('customer_profiles'):
        sqlmodel.SQLModel.metadata.create_all(connection, checkfirst=True)
        return

    op.add_column('customer_profiles', sa.Column('company_id', sa.UUID(), nullable=True))
    op.add_column('customer_profiles', sa.Column('contact_email', sqlmodel.sql.sqltypes.AutoString(length=320), nullable=True))
    op.add_column('customer_profiles', sa.Column('status', sa.String(length=32), server_default='healthy', nullable=False))
    op.add_column('customer_profiles', sa.Column('mrr', sa.Float(), server_default='0', nullable=False))
    op.add_column('customer_profiles', sa.Column('last_contact', sa.DateTime(timezone=True), nullable=True))
    op.add_column('customer_profiles', sa.Column('tags', sa.ARRAY(sa.String()), nullable=True))
    op.add_column('customer_profiles', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('customer_profiles', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.create_index('ix_customer_profiles_company_id', 'customer_profiles', ['company_id'], unique=False)
    op.create_index('ix_customer_profiles_company_status', 'customer_profiles', ['company_id', 'status'], unique=False)
    op.create_foreign_key('fk_customer_profiles_company_id_users', 'customer_profiles', 'users', ['company_id'], ['id'], ondelete='SET NULL')
    op.add_column('users', sa.Column('company_name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True))
    op.add_column('users', sa.Column('plan', sa.String(length=50), server_default='free', nullable=False))
    op.add_column('users', sa.Column('suspended', sa.Boolean(), server_default='false', nullable=False))
    op.alter_column('users', 'role',
               existing_type=sa.VARCHAR(length=6),
               type_=sa.Enum('admin', 'company', 'csm', 'viewer', name='user_role', native_enum=False),
               existing_nullable=False,
               existing_server_default=sa.text("'viewer'::character varying"),
               server_default=sa.text("'company'::character varying"))


def downgrade() -> None:
    op.alter_column('users', 'role',
               existing_type=sa.Enum('admin', 'company', 'csm', 'viewer', name='user_role', native_enum=False),
               type_=sa.VARCHAR(length=6),
               existing_nullable=False,
               existing_server_default=sa.text("'company'::character varying"),
               server_default=sa.text("'viewer'::character varying"))
    op.drop_column('users', 'suspended')
    op.drop_column('users', 'plan')
    op.drop_column('users', 'company_name')
    op.drop_constraint('fk_customer_profiles_company_id_users', 'customer_profiles', type_='foreignkey')
    op.drop_index('ix_customer_profiles_company_status', table_name='customer_profiles')
    op.drop_index('ix_customer_profiles_company_id', table_name='customer_profiles')
    op.drop_column('customer_profiles', 'created_at')
    op.drop_column('customer_profiles', 'notes')
    op.drop_column('customer_profiles', 'tags')
    op.drop_column('customer_profiles', 'last_contact')
    op.drop_column('customer_profiles', 'mrr')
    op.drop_column('customer_profiles', 'status')
    op.drop_column('customer_profiles', 'contact_email')
    op.drop_column('customer_profiles', 'company_id')
