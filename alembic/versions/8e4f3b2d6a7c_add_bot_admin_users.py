"""add bot_admin_users table

Revision ID: 8e4f3b2d6a7c
Revises: 7d3f2a1c5e9b
Create Date: 2025-04-24

"""
from alembic import op
import sqlalchemy as sa

revision = '8e4f3b2d6a7c'
down_revision = '7d3f2a1c5e9b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('bot_admin_users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bot_id', sa.BigInteger(), nullable=True),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('username', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_bot_admin_users_bot_id', 'bot_admin_users', ['bot_id'], unique=False)
    op.create_index('ix_bot_admin_users_user_id', 'bot_admin_users', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_bot_admin_users_user_id', table_name='bot_admin_users')
    op.drop_index('ix_bot_admin_users_bot_id', table_name='bot_admin_users')
    op.drop_table('bot_admin_users')