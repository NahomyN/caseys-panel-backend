"""Add supplemental indexes

Revision ID: 002
Revises: 001
Create Date: 2025-08-27 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def safe_drop_index(index_name: str, table_name: str):
    """Safely drop an index, ignoring if it doesn't exist."""
    try:
        op.drop_index(index_name, table_name=table_name)
    except Exception:
        # Index doesn't exist or already dropped
        pass


def upgrade() -> None:
    op.create_index('ix_checkpoints_run_node', 'checkpoints', ['run_id', 'node_key'], unique=False)
    op.create_index('ix_canvases_patient_agent', 'canvases', ['patient_id', 'agent_no'], unique=False)
    op.create_index('ix_events_run_node_time', 'events', ['run_id', 'node_key', 'created_at'], unique=False)
    op.create_index('ix_workflow_runs_patient_active', 'workflow_runs', ['patient_id', 'status'], unique=False)


def downgrade() -> None:
    safe_drop_index('ix_workflow_runs_patient_active', 'workflow_runs')
    safe_drop_index('ix_events_run_node_time', 'events')
    safe_drop_index('ix_canvases_patient_agent', 'canvases')
    safe_drop_index('ix_checkpoints_run_node', 'checkpoints')
