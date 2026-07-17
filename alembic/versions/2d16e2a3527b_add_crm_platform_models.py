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

    profile_columns = {
        column['name'] for column in inspector.get_columns('customer_profiles')
    }
    profile_additions = (
        ('company_id', sa.UUID(), True, None),
        ('contact_email', sqlmodel.sql.sqltypes.AutoString(length=320), True, None),
        ('status', sa.String(length=32), False, 'healthy'),
        ('mrr', sa.Float(), False, '0'),
        ('last_contact', sa.DateTime(timezone=True), True, None),
        ('tags', sa.ARRAY(sa.String()), True, None),
        ('notes', sa.Text(), True, None),
        ('created_at', sa.DateTime(timezone=True), False, sa.text('now()')),
    )
    for name, column_type, nullable, default in profile_additions:
        if name not in profile_columns:
            op.add_column(
                'customer_profiles',
                sa.Column(name, column_type, nullable=nullable, server_default=default),
            )

    index_names = {
        index['name'] for index in inspector.get_indexes('customer_profiles')
    }
    if 'ix_customer_profiles_company_id' not in index_names:
        op.create_index(
            'ix_customer_profiles_company_id',
            'customer_profiles',
            ['company_id'],
            unique=False,
        )
    if 'ix_customer_profiles_company_status' not in index_names:
        op.create_index(
            'ix_customer_profiles_company_status',
            'customer_profiles',
            ['company_id', 'status'],
            unique=False,
        )

    company_fk_exists = any(
        foreign_key['constrained_columns'] == ['company_id']
        and foreign_key['referred_table'] == 'users'
        for foreign_key in inspector.get_foreign_keys('customer_profiles')
    )
    if not company_fk_exists:
        op.create_foreign_key(
            'fk_customer_profiles_company_id_users',
            'customer_profiles',
            'users',
            ['company_id'],
            ['id'],
            ondelete='SET NULL',
        )

    user_columns = {column['name'] for column in inspector.get_columns('users')}
    user_additions = (
        ('company_name', sqlmodel.sql.sqltypes.AutoString(length=255), True, None),
        ('plan', sa.String(length=50), False, 'free'),
        ('suspended', sa.Boolean(), False, 'false'),
    )
    has_legacy_user_schema = any(name not in user_columns for name, *_ in user_additions)
    for name, column_type, nullable, default in user_additions:
        if name not in user_columns:
            op.add_column(
                'users',
                sa.Column(name, column_type, nullable=nullable, server_default=default),
            )
    if has_legacy_user_schema:
        op.alter_column(
            'users',
            'role',
            existing_type=sa.VARCHAR(length=6),
            type_=sa.Enum(
                'admin', 'company', 'csm', 'viewer', name='user_role', native_enum=False
            ),
            existing_nullable=False,
            existing_server_default=sa.text("'viewer'::character varying"),
            server_default=sa.text("'company'::character varying"),
        )


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
