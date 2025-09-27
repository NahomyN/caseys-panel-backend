"""Add tenant/date index to daily_run_stats

Revision ID: 009_add_index_daily_run_stats
Revises: 008_tenant_for_attachments_audit_and_daily_stats
Create Date: 2025-08-28 15:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '009_add_index_daily_run_stats'
down_revision: Union[str, None] = '008_tenant_for_attachments_audit_and_daily_stats'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    # Idempotent creation
    if dialect == 'sqlite':
        existing = [r[1] for r in bind.execute(sa.text("PRAGMA index_list('daily_run_stats')"))]
        if 'ix_daily_run_stats_tenant_date' not in existing:
            op.create_index('ix_daily_run_stats_tenant_date', 'daily_run_stats', ['tenant_id','date'])
    else:
        op.create_index('ix_daily_run_stats_tenant_date', 'daily_run_stats', ['tenant_id','date'])

def downgrade() -> None:
    op.drop_index('ix_daily_run_stats_tenant_date', table_name='daily_run_stats')
