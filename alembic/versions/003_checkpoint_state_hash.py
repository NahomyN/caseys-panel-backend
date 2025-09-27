"""Add state_hash to checkpoints for dedupe

Revision ID: 003
Revises: 002
Create Date: 2025-08-27 13:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '003'
down_revision = ('002', '002b')
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    add_col = True
    if dialect == 'sqlite':
        res = bind.execute(sa.text("PRAGMA table_info('checkpoints')"))
        existing = {r[1] for r in res}
        if 'state_hash' in existing:
            add_col = False
    if add_col:
        op.add_column('checkpoints', sa.Column('state_hash', sa.String(), nullable=True))
    # Create index if not exists (SQLite doesn't support IF NOT EXISTS for CREATE INDEX via SQLAlchemy)
    if dialect == 'sqlite':
        existing_indexes = [r[1] for r in bind.execute(sa.text("PRAGMA index_list('checkpoints')"))]
        if 'ix_checkpoints_state_hash' not in existing_indexes:
            op.create_index('ix_checkpoints_state_hash', 'checkpoints', ['state_hash'])
    else:
        op.create_index('ix_checkpoints_state_hash', 'checkpoints', ['state_hash'])
    if dialect == 'sqlite':
        # Recreate table with unique constraint via batch
        with op.batch_alter_table('checkpoints') as batch_op:
            batch_op.create_unique_constraint('uq_checkpoint_dedup', ['run_id', 'node_key', 'state_hash'])
    else:
        op.create_unique_constraint('uq_checkpoint_dedup', 'checkpoints', ['run_id', 'node_key', 'state_hash'])


def downgrade() -> None:
    # SQLite drop in batch mode
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == 'sqlite':
        with op.batch_alter_table('checkpoints') as batch_op:
            batch_op.drop_constraint('uq_checkpoint_dedup', type_='unique')
    else:
        op.drop_constraint('uq_checkpoint_dedup', 'checkpoints', type_='unique')
    op.drop_index('ix_checkpoints_state_hash', table_name='checkpoints')
    op.drop_column('checkpoints', 'state_hash')
