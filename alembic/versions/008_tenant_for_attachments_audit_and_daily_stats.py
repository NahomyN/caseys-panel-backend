"""Add tenant columns to attachments/audit_logs and tenant dimension to daily_run_stats

Revision ID: 008_tenant_for_attachments_audit_and_daily_stats
Revises: 007_add_tenant_columns
Create Date: 2025-08-28 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '008_tenant_for_attachments_audit_and_daily_stats'
down_revision: Union[str, None] = '007_add_tenant_columns'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    def _has_col(table, col):
        if dialect == 'sqlite':
            rows = bind.execute(sa.text(f"PRAGMA table_info('{table}')"))
            return col in {r[1] for r in rows}
        insp = sa.inspect(bind)
        return col in [c['name'] for c in insp.get_columns(table)]

    # attachments tenant_id
    if not _has_col('attachments', 'tenant_id'):
        with op.batch_alter_table('attachments') as batch_op:
            batch_op.add_column(sa.Column('tenant_id', sa.String(), nullable=False, server_default='default'))
            batch_op.create_index('ix_attachments_tenant_id', ['tenant_id'])
    # audit_logs tenant_id
    if not _has_col('audit_logs', 'tenant_id'):
        with op.batch_alter_table('audit_logs') as batch_op:
            batch_op.add_column(sa.Column('tenant_id', sa.String(), nullable=False, server_default='default'))
            batch_op.create_index('ix_audit_logs_tenant_id', ['tenant_id'])

    # daily_run_stats modification
    has_tenant = _has_col('daily_run_stats', 'tenant_id')
    if dialect == 'sqlite':
        # Recreate table if tenant column missing or PK not composite
        if not has_tenant:
            op.rename_table('daily_run_stats', 'daily_run_stats_old_tmp')
            op.create_table(
                'daily_run_stats',
                sa.Column('date', sa.String(), nullable=False),
                sa.Column('tenant_id', sa.String(), nullable=False, server_default='default'),
                sa.Column('runs_started', sa.Integer(), nullable=False, default=0),
                sa.Column('runs_completed', sa.Integer(), nullable=False, default=0),
                sa.Column('avg_total_duration_ms', sa.Integer(), nullable=True),
                sa.Column('failures', sa.Integer(), nullable=False, default=0),
                sa.Column('fallbacks_used', sa.Integer(), nullable=False, default=0),
                sa.PrimaryKeyConstraint('date', 'tenant_id')
            )
            # migrate existing rows
            bind.execute(sa.text("""
                INSERT INTO daily_run_stats (date, tenant_id, runs_started, runs_completed, avg_total_duration_ms, failures, fallbacks_used)
                SELECT date, 'default', runs_started, runs_completed, avg_total_duration_ms, failures, fallbacks_used
                FROM daily_run_stats_old_tmp
            """))
            op.drop_table('daily_run_stats_old_tmp')
    else:
        if not has_tenant:
            with op.batch_alter_table('daily_run_stats') as batch_op:
                batch_op.add_column(sa.Column('tenant_id', sa.String(), server_default='default', nullable=True))
            op.execute("UPDATE daily_run_stats SET tenant_id='default' WHERE tenant_id IS NULL")
            with op.batch_alter_table('daily_run_stats') as batch_op:
                # drop old single-column PK if exists
                try:
                    batch_op.drop_constraint('daily_run_stats_pkey', type_='primary')
                except Exception:
                    pass
                batch_op.alter_column('tenant_id', existing_type=sa.String(), nullable=False)
                batch_op.create_primary_key('daily_run_stats_pkey', ['date', 'tenant_id'])


def downgrade() -> None:
    # Revert daily_run_stats composite key to single date PK
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == 'sqlite':
        # Recreate without tenant dimension (data collapse risk: choose first per date)
        op.rename_table('daily_run_stats', 'daily_run_stats_new_tmp')
        op.create_table(
            'daily_run_stats',
            sa.Column('date', sa.String(), nullable=False),
            sa.Column('runs_started', sa.Integer(), nullable=False, default=0),
            sa.Column('runs_completed', sa.Integer(), nullable=False, default=0),
            sa.Column('avg_total_duration_ms', sa.Integer(), nullable=True),
            sa.Column('failures', sa.Integer(), nullable=False, default=0),
            sa.Column('fallbacks_used', sa.Integer(), nullable=False, default=0),
            sa.PrimaryKeyConstraint('date')
        )
        # pick aggregate per date (sum) when collapsing tenants
        bind.execute(sa.text("""
            INSERT INTO daily_run_stats (date, runs_started, runs_completed, avg_total_duration_ms, failures, fallbacks_used)
            SELECT date, SUM(runs_started), SUM(runs_completed), AVG(avg_total_duration_ms), SUM(failures), SUM(fallbacks_used)
            FROM daily_run_stats_new_tmp GROUP BY date
        """))
        op.drop_table('daily_run_stats_new_tmp')
    else:
        with op.batch_alter_table('daily_run_stats', schema=None) as batch_op:
            batch_op.drop_constraint('daily_run_stats_pkey', type_='primary')
            batch_op.create_primary_key('daily_run_stats_pkey', ['date'])
            batch_op.drop_column('tenant_id')

    # Drop tenant columns from audit_logs and attachments
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_index('ix_audit_logs_tenant_id')
        batch_op.drop_column('tenant_id')
    with op.batch_alter_table('attachments', schema=None) as batch_op:
        batch_op.drop_index('ix_attachments_tenant_id')
        batch_op.drop_column('tenant_id')
