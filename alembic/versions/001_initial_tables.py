"""Initial tables

Revision ID: 001
Revises: 
Create Date: 2025-08-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('workflow_runs',
    sa.Column('run_id', sa.String(), nullable=False),
    sa.Column('patient_id', sa.String(), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', name='workflowstatus'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
    sa.PrimaryKeyConstraint('run_id')
    )
    op.create_index(op.f('ix_workflow_runs_patient_id'), 'workflow_runs', ['patient_id'], unique=False)
    
    op.create_table('attachments',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('patient_id', sa.String(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('uri', sa.String(), nullable=False),
    sa.Column('size', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_attachments_patient_id'), 'attachments', ['patient_id'], unique=False)
    
    op.create_table('audit_logs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('actor', sa.String(), nullable=False),
    sa.Column('action', sa.String(), nullable=False),
    sa.Column('patient_id', sa.String(), nullable=True),
    sa.Column('details_json', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_patient_id'), 'audit_logs', ['patient_id'], unique=False)
    
    op.create_table('canvases',
    sa.Column('patient_id', sa.String(), nullable=False),
    sa.Column('agent_no', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('content_md', sa.Text(), nullable=False),
    sa.Column('content_json', sa.JSON(), nullable=True),
    sa.Column('updated_by', sa.String(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
    sa.PrimaryKeyConstraint('patient_id', 'agent_no')
    )
    
    op.create_table('checkpoints',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('run_id', sa.String(), nullable=False),
    sa.Column('node_key', sa.String(), nullable=False),
    sa.Column('state_json', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
    sa.ForeignKeyConstraint(['run_id'], ['workflow_runs.run_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('events',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('run_id', sa.String(), nullable=False),
    sa.Column('node_key', sa.String(), nullable=False),
    sa.Column('event_type', sa.Enum('NODE_STARTED', 'NODE_PROGRESS', 'NODE_COMPLETED', 'NODE_FAILED', 'NODE_RETRIED', name='eventtype'), nullable=False),
    sa.Column('event_payload_json', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
    sa.ForeignKeyConstraint(['run_id'], ['workflow_runs.run_id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('events')
    op.drop_table('checkpoints')
    op.drop_table('canvases')
    op.drop_index(op.f('ix_audit_logs_patient_id'), table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_index(op.f('ix_attachments_patient_id'), table_name='attachments')
    op.drop_table('attachments')
    op.drop_index(op.f('ix_workflow_runs_patient_id'), table_name='workflow_runs')
    op.drop_table('workflow_runs')