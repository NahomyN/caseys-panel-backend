"""Add run_node_metrics table

Revision ID: dde00df6f577
Revises: 003
Create Date: 2025-08-28 00:16:51.980924

"""
from alembic import op
import sqlalchemy as sa


revision = 'dde00df6f577'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create run_node_metrics table
    op.create_table(
        'run_node_metrics',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('run_id', sa.String(), nullable=False),
        sa.Column('node_key', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('success_duration_ms', sa.Integer(), nullable=True),
        sa.Column('failure_duration_ms', sa.Integer(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False, default=0),
        sa.Column('retries', sa.Integer(), nullable=False, default=0),
        sa.Column('fallback_used', sa.Integer(), nullable=False, default=0),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['run_id'], ['workflow_runs.run_id']),
        sa.UniqueConstraint('run_id', 'node_key', name='uq_run_node_metrics')
    )
    
    # Create indexes
    op.create_index('ix_run_node_metrics_run_id', 'run_node_metrics', ['run_id'])
    op.create_index('ix_run_node_metrics_run_status', 'run_node_metrics', ['run_id', 'status'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_run_node_metrics_run_status', table_name='run_node_metrics')
    op.drop_index('ix_run_node_metrics_run_id', table_name='run_node_metrics')
    
    # Drop table
    op.drop_table('run_node_metrics')