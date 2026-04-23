"""add bot_id to operators

Revision ID: 7d3f2a1c5e9b
Revises: a24c260d69e6
Create Date: 2025-04-24

"""
from alembic import op
import sqlalchemy as sa

revision = '7d3f2a1c5e9b'
down_revision = 'a24c260d69e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('operators', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bot_id', sa.BigInteger(), nullable=True))
        batch_op.create_index('ix_operators_bot_id', ['bot_id'], unique=False)

def downgrade() -> None:
    with op.batch_alter_table('operators', schema=None) as batch_op:
        batch_op.drop_index('ix_operators_bot_id')
        batch_op.drop_column('bot_id')