"""Workflow Engine - AI Workflow Definitions and Execution

Revision ID: 013_workflow_engine
Revises: 012_artifact_management
Create Date: 2025-09-21 20:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '013_workflow_engine'
down_revision = '012_artifact_management'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create custom types for workflow management
    op.execute("""
        CREATE TYPE workflow_status AS ENUM (
            'draft',
            'active',
            'deprecated',
            'archived'
        );
    """)

    op.execute("""
        CREATE TYPE workflow_run_status AS ENUM (
            'queued',
            'running',
            'paused',
            'completed',
            'failed',
            'cancelled',
            'timeout'
        );
    """)

    op.execute("""
        CREATE TYPE step_status AS ENUM (
            'pending',
            'running',
            'completed',
            'failed',
            'skipped',
            'cancelled'
        );
    """)

    op.execute("""
        CREATE TYPE step_type AS ENUM (
            'data_collection',
            'ai_analysis',
            'human_review',
            'decision_point',
            'notification',
            'integration',
            'validation',
            'documentation'
        );
    """)

    # Create workflows table for workflow definitions/templates
    op.create_table('workflows',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                 server_default=sa.text('uuid_generate_v4()')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('version', sa.String(20), nullable=False, default='1.0.0'),
        sa.Column('status', sa.Enum('draft', 'active', 'deprecated', 'archived',
                                   name='workflow_status'), nullable=False, default='draft'),
        sa.Column('definition', sa.JSON, nullable=False),  # Workflow DAG definition
        sa.Column('input_schema', sa.JSON, default={}),  # Expected input structure
        sa.Column('output_schema', sa.JSON, default={}),  # Expected output structure
        sa.Column('triggers', sa.JSON, default={}),  # Event triggers
        sa.Column('parameters', sa.JSON, default={}),  # Default parameters
        sa.Column('timeout_minutes', sa.Integer, default=60),
        sa.Column('max_retries', sa.Integer, default=3),
        sa.Column('tags', sa.ARRAY(sa.String(50)), default=[]),
        sa.Column('specialty', sa.String(100)),  # Medical specialty
        sa.Column('use_cases', sa.ARRAY(sa.String(100)), default=[]),
        sa.Column('created_by', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('users.id'), nullable=False),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('users.id'), nullable=False),
        sa.Column('approved_by', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('users.id'), nullable=True),
        sa.Column('approved_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('metrics', sa.JSON, default={}),  # Performance metrics
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint('organization_id', 'name', 'version',
                           name='unique_org_workflow_version')
    )

    # Create workflow_runs table for execution instances
    op.create_table('workflow_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                 server_default=sa.text('uuid_generate_v4()')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('workflow_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('workflows.id'), nullable=False),
        sa.Column('case_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('cases.id'), nullable=False),
        sa.Column('patient_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('started_by', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('users.id'), nullable=False),
        sa.Column('run_number', sa.String(50), nullable=False),
        sa.Column('status', sa.Enum('queued', 'running', 'paused', 'completed',
                                   'failed', 'cancelled', 'timeout',
                                   name='workflow_run_status'), nullable=False, default='queued'),
        sa.Column('input_data', sa.JSON, default={}),
        sa.Column('output_data', sa.JSON, default={}),
        sa.Column('context', sa.JSON, default={}),  # Runtime context
        sa.Column('error_details', sa.JSON),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('completed_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('duration_seconds', sa.Integer),
        sa.Column('retry_count', sa.Integer, default=0),
        sa.Column('priority', sa.Integer, default=5),  # 1-10 scale
        sa.Column('scheduled_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('timeout_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('metrics', sa.JSON, default={}),  # Performance metrics
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('organization_id', 'run_number',
                           name='unique_org_run_number')
    )

    # Create workflow_steps table for individual step execution
    op.create_table('workflow_steps',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                 server_default=sa.text('uuid_generate_v4()')),
        sa.Column('workflow_run_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('workflow_runs.id'), nullable=False),
        sa.Column('step_name', sa.String(255), nullable=False),
        sa.Column('step_type', sa.Enum('data_collection', 'ai_analysis', 'human_review',
                                      'decision_point', 'notification', 'integration',
                                      'validation', 'documentation', name='step_type'),
                 nullable=False),
        sa.Column('status', sa.Enum('pending', 'running', 'completed', 'failed',
                                   'skipped', 'cancelled', name='step_status'),
                 nullable=False, default='pending'),
        sa.Column('sequence_order', sa.Integer, nullable=False),
        sa.Column('depends_on', sa.ARRAY(sa.String(255)), default=[]),  # Step dependencies
        sa.Column('configuration', sa.JSON, default={}),
        sa.Column('input_data', sa.JSON, default={}),
        sa.Column('output_data', sa.JSON, default={}),
        sa.Column('error_details', sa.JSON),
        sa.Column('assigned_to', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('users.id'), nullable=True),  # For human review steps
        sa.Column('started_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('completed_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('duration_seconds', sa.Integer),
        sa.Column('retry_count', sa.Integer, default=0),
        sa.Column('ai_model_used', sa.String(100)),
        sa.Column('confidence_score', sa.Float),
        sa.Column('metrics', sa.JSON, default={}),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP'))
    )

    # Create workflow_step_artifacts junction table
    op.create_table('workflow_step_artifacts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                 server_default=sa.text('uuid_generate_v4()')),
        sa.Column('workflow_step_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('workflow_steps.id'), nullable=False),
        sa.Column('artifact_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('artifacts.id'), nullable=False),
        sa.Column('role', sa.String(50), nullable=False),  # input, output, reference
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('workflow_step_id', 'artifact_id', 'role',
                           name='unique_step_artifact_role')
    )

    # Create workflow_queues for distributed processing
    op.create_table('workflow_queues',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                 server_default=sa.text('uuid_generate_v4()')),
        sa.Column('queue_name', sa.String(100), nullable=False, unique=True),
        sa.Column('description', sa.Text),
        sa.Column('max_concurrent', sa.Integer, default=10),
        sa.Column('priority_weight', sa.Integer, default=1),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('worker_config', sa.JSON, default={}),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP'))
    )

    # Create indexes for performance
    op.create_index('idx_workflows_org_status', 'workflows',
                   ['organization_id', 'status'])
    op.create_index('idx_workflows_specialty', 'workflows', ['specialty'])
    op.create_index('idx_workflows_tags', 'workflows', ['tags'], postgresql_using='gin')
    op.create_index('idx_workflows_created_by', 'workflows', ['created_by'])

    op.create_index('idx_workflow_runs_org_status', 'workflow_runs',
                   ['organization_id', 'status'])
    op.create_index('idx_workflow_runs_workflow', 'workflow_runs', ['workflow_id'])
    op.create_index('idx_workflow_runs_case', 'workflow_runs', ['case_id'])
    op.create_index('idx_workflow_runs_patient', 'workflow_runs', ['patient_id'])
    op.create_index('idx_workflow_runs_started_by', 'workflow_runs', ['started_by'])
    op.create_index('idx_workflow_runs_created', 'workflow_runs', ['created_at'])
    op.create_index('idx_workflow_runs_priority_status', 'workflow_runs',
                   ['priority', 'status'])

    op.create_index('idx_workflow_steps_run_sequence', 'workflow_steps',
                   ['workflow_run_id', 'sequence_order'])
    op.create_index('idx_workflow_steps_status', 'workflow_steps', ['status'])
    op.create_index('idx_workflow_steps_type', 'workflow_steps', ['step_type'])
    op.create_index('idx_workflow_steps_assigned_to', 'workflow_steps',
                   ['assigned_to'])

    op.create_index('idx_workflow_step_artifacts_step', 'workflow_step_artifacts',
                   ['workflow_step_id'])
    op.create_index('idx_workflow_step_artifacts_artifact', 'workflow_step_artifacts',
                   ['artifact_id'])

    op.create_index('idx_workflow_queues_active', 'workflow_queues', ['is_active'])

    # Enable Row Level Security
    op.execute('ALTER TABLE workflows ENABLE ROW LEVEL SECURITY;')
    op.execute('ALTER TABLE workflow_runs ENABLE ROW LEVEL SECURITY;')
    op.execute('ALTER TABLE workflow_steps ENABLE ROW LEVEL SECURITY;')
    op.execute('ALTER TABLE workflow_step_artifacts ENABLE ROW LEVEL SECURITY;')

    # Create RLS policies
    op.execute("""
        CREATE POLICY workflow_org_isolation ON workflows
        FOR ALL TO app_role
        USING (organization_id = current_setting('app.current_org_id', true)::uuid);
    """)

    op.execute("""
        CREATE POLICY workflow_runs_org_isolation ON workflow_runs
        FOR ALL TO app_role
        USING (organization_id = current_setting('app.current_org_id', true)::uuid);
    """)

    op.execute("""
        CREATE POLICY workflow_steps_run_access ON workflow_steps
        FOR ALL TO app_role
        USING (
            EXISTS (
                SELECT 1 FROM workflow_runs wr
                WHERE wr.id = workflow_steps.workflow_run_id
                AND wr.organization_id = current_setting('app.current_org_id', true)::uuid
            )
        );
    """)

    op.execute("""
        CREATE POLICY workflow_step_artifacts_step_access ON workflow_step_artifacts
        FOR ALL TO app_role
        USING (
            EXISTS (
                SELECT 1 FROM workflow_steps ws
                JOIN workflow_runs wr ON wr.id = ws.workflow_run_id
                WHERE ws.id = workflow_step_artifacts.workflow_step_id
                AND wr.organization_id = current_setting('app.current_org_id', true)::uuid
            )
        );
    """)

    # Add updated_at triggers
    op.execute("""
        CREATE TRIGGER update_workflows_updated_at
        BEFORE UPDATE ON workflows
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    op.execute("""
        CREATE TRIGGER update_workflow_runs_updated_at
        BEFORE UPDATE ON workflow_runs
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    op.execute("""
        CREATE TRIGGER update_workflow_steps_updated_at
        BEFORE UPDATE ON workflow_steps
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    op.execute("""
        CREATE TRIGGER update_workflow_queues_updated_at
        BEFORE UPDATE ON workflow_queues
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # Create function for workflow run number generation
    op.execute("""
        CREATE OR REPLACE FUNCTION generate_workflow_run_number(org_id uuid)
        RETURNS text AS $$
        DECLARE
            year_prefix text := EXTRACT(YEAR FROM CURRENT_DATE)::text;
            month_prefix text := lpad(EXTRACT(MONTH FROM CURRENT_DATE)::text, 2, '0');
            sequence_num integer;
            run_number text;
        BEGIN
            SELECT COALESCE(MAX(
                CASE
                    WHEN run_number ~ ('^WR-' || year_prefix || month_prefix || '-[0-9]+$')
                    THEN substring(run_number from (length('WR-' || year_prefix || month_prefix) + 2))::integer
                    ELSE 0
                END
            ), 0) + 1
            INTO sequence_num
            FROM workflow_runs
            WHERE organization_id = org_id
            AND run_number LIKE 'WR-' || year_prefix || month_prefix || '-%';

            run_number := 'WR-' || year_prefix || month_prefix || '-' || lpad(sequence_num::text, 6, '0');
            RETURN run_number;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create workflow analytics view
    op.execute("""
        CREATE OR REPLACE VIEW workflow_analytics AS
        SELECT
            w.id as workflow_id,
            w.name as workflow_name,
            w.organization_id,
            COUNT(wr.id) as total_runs,
            COUNT(CASE WHEN wr.status = 'completed' THEN 1 END) as completed_runs,
            COUNT(CASE WHEN wr.status = 'failed' THEN 1 END) as failed_runs,
            AVG(wr.duration_seconds) as avg_duration_seconds,
            MIN(wr.duration_seconds) as min_duration_seconds,
            MAX(wr.duration_seconds) as max_duration_seconds,
            AVG(CASE WHEN wr.status = 'completed' THEN wr.duration_seconds END) as avg_success_duration,
            COUNT(wr.id) FILTER (WHERE wr.created_at >= CURRENT_DATE - INTERVAL '30 days') as runs_last_30_days,
            COUNT(wr.id) FILTER (WHERE wr.created_at >= CURRENT_DATE - INTERVAL '7 days') as runs_last_7_days
        FROM workflows w
        LEFT JOIN workflow_runs wr ON w.id = wr.workflow_id
        WHERE w.deleted_at IS NULL
        GROUP BY w.id, w.name, w.organization_id;
    """)

    # Insert default workflow queues
    op.execute("""
        INSERT INTO workflow_queues (queue_name, description, max_concurrent, priority_weight) VALUES
        ('ai_analysis', 'AI analysis and processing tasks', 5, 3),
        ('human_review', 'Tasks requiring human review', 20, 2),
        ('notifications', 'Notification and alert tasks', 10, 1),
        ('data_processing', 'Data collection and processing', 8, 2),
        ('integrations', 'External system integrations', 3, 1);
    """)


def downgrade() -> None:
    # Drop view
    op.execute('DROP VIEW IF EXISTS workflow_analytics;')

    # Drop function
    op.execute('DROP FUNCTION IF EXISTS generate_workflow_run_number(uuid);')

    # Drop triggers
    op.execute('DROP TRIGGER IF EXISTS update_workflow_queues_updated_at ON workflow_queues;')
    op.execute('DROP TRIGGER IF EXISTS update_workflow_steps_updated_at ON workflow_steps;')
    op.execute('DROP TRIGGER IF EXISTS update_workflow_runs_updated_at ON workflow_runs;')
    op.execute('DROP TRIGGER IF EXISTS update_workflows_updated_at ON workflows;')

    # Drop RLS policies
    op.execute('DROP POLICY IF EXISTS workflow_step_artifacts_step_access ON workflow_step_artifacts;')
    op.execute('DROP POLICY IF EXISTS workflow_steps_run_access ON workflow_steps;')
    op.execute('DROP POLICY IF EXISTS workflow_runs_org_isolation ON workflow_runs;')
    op.execute('DROP POLICY IF EXISTS workflow_org_isolation ON workflows;')

    # Drop tables
    op.drop_table('workflow_queues')
    op.drop_table('workflow_step_artifacts')
    op.drop_table('workflow_steps')
    op.drop_table('workflow_runs')
    op.drop_table('workflows')

    # Drop custom types
    op.execute('DROP TYPE IF EXISTS step_type;')
    op.execute('DROP TYPE IF EXISTS step_status;')
    op.execute('DROP TYPE IF EXISTS workflow_run_status;')
    op.execute('DROP TYPE IF EXISTS workflow_status;')