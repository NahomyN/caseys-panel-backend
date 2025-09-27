"""Clinical Data - Patients, Cases, and Collaboration

Revision ID: 011_clinical_data
Revises: 010_core_infrastructure
Create Date: 2025-09-21 20:15:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '011_clinical_data'
down_revision = '010_core_infrastructure'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create custom types for clinical data
    op.execute("""
        CREATE TYPE case_status AS ENUM (
            'draft',
            'active',
            'pending_review',
            'completed',
            'archived',
            'cancelled'
        );
    """)

    op.execute("""
        CREATE TYPE case_priority AS ENUM (
            'low',
            'normal',
            'high',
            'urgent',
            'critical'
        );
    """)

    op.execute("""
        CREATE TYPE gender AS ENUM (
            'male',
            'female',
            'other',
            'unknown'
        );
    """)

    # Create patients table (PHI data)
    op.create_table('patients',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                 server_default=sa.text('uuid_generate_v4()')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('medical_record_number', sa.String(50), nullable=False),
        sa.Column('first_name', sa.String(100), nullable=False),
        sa.Column('last_name', sa.String(100), nullable=False),
        sa.Column('middle_name', sa.String(100)),
        sa.Column('date_of_birth', sa.Date, nullable=False),
        sa.Column('gender', sa.Enum('male', 'female', 'other', 'unknown',
                                   name='gender'), nullable=False),
        sa.Column('phone', sa.String(20)),
        sa.Column('email', sa.String(255)),
        sa.Column('address', sa.JSON),
        sa.Column('emergency_contact', sa.JSON),
        sa.Column('insurance_info', sa.JSON),
        sa.Column('medical_history', sa.JSON),
        sa.Column('allergies', sa.JSON),
        sa.Column('medications', sa.JSON),
        sa.Column('is_active', sa.Boolean, nullable=False, default=True),
        sa.Column('metadata', sa.JSON, default={}),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint('organization_id', 'medical_record_number',
                           name='unique_org_mrn')
    )

    # Create cases table
    op.create_table('cases',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                 server_default=sa.text('uuid_generate_v4()')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('patient_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('assigned_user_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('users.id'), nullable=False),
        sa.Column('case_number', sa.String(50), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('status', sa.Enum('draft', 'active', 'pending_review',
                                   'completed', 'archived', 'cancelled',
                                   name='case_status'), nullable=False, default='draft'),
        sa.Column('priority', sa.Enum('low', 'normal', 'high', 'urgent', 'critical',
                                     name='case_priority'), nullable=False, default='normal'),
        sa.Column('chief_complaint', sa.Text),
        sa.Column('history_present_illness', sa.Text),
        sa.Column('physical_examination', sa.Text),
        sa.Column('assessment_plan', sa.Text),
        sa.Column('differential_diagnosis', sa.JSON),
        sa.Column('lab_results', sa.JSON),
        sa.Column('imaging_results', sa.JSON),
        sa.Column('treatment_plan', sa.JSON),
        sa.Column('follow_up_instructions', sa.Text),
        sa.Column('admit_date', sa.TIMESTAMP(timezone=True)),
        sa.Column('discharge_date', sa.TIMESTAMP(timezone=True)),
        sa.Column('estimated_completion', sa.TIMESTAMP(timezone=True)),
        sa.Column('actual_completion', sa.TIMESTAMP(timezone=True)),
        sa.Column('tags', sa.ARRAY(sa.String(50)), default=[]),
        sa.Column('metadata', sa.JSON, default={}),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint('organization_id', 'case_number',
                           name='unique_org_case_number')
    )

    # Create case_collaborators table for multi-user access
    op.create_table('case_collaborators',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                 server_default=sa.text('uuid_generate_v4()')),
        sa.Column('case_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('cases.id'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('users.id'), nullable=False),
        sa.Column('access_level', sa.Enum('read', 'write', 'admin',
                                         name='access_level'), nullable=False),
        sa.Column('added_by', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('users.id'), nullable=False),
        sa.Column('notes', sa.Text),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint('case_id', 'user_id', name='unique_case_user')
    )

    # Create case_notes table for detailed documentation
    op.create_table('case_notes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                 server_default=sa.text('uuid_generate_v4()')),
        sa.Column('case_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('cases.id'), nullable=False),
        sa.Column('author_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('users.id'), nullable=False),
        sa.Column('note_type', sa.String(50), nullable=False),
        sa.Column('subject', sa.String(255)),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('is_private', sa.Boolean, default=False),
        sa.Column('metadata', sa.JSON, default={}),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True), nullable=True)
    )

    # Create indexes for performance optimization
    op.create_index('idx_patients_org_active', 'patients',
                   ['organization_id', 'is_active'])
    op.create_index('idx_patients_mrn', 'patients', ['medical_record_number'])
    op.create_index('idx_patients_name', 'patients',
                   ['last_name', 'first_name'])
    op.create_index('idx_patients_dob', 'patients', ['date_of_birth'])

    op.create_index('idx_cases_org_status', 'cases',
                   ['organization_id', 'status'])
    op.create_index('idx_cases_patient', 'cases', ['patient_id'])
    op.create_index('idx_cases_assigned_user', 'cases', ['assigned_user_id'])
    op.create_index('idx_cases_priority_status', 'cases',
                   ['priority', 'status'])
    op.create_index('idx_cases_created', 'cases', ['created_at'])
    op.create_index('idx_cases_tags', 'cases', ['tags'], postgresql_using='gin')

    op.create_index('idx_case_collaborators_case', 'case_collaborators',
                   ['case_id'])
    op.create_index('idx_case_collaborators_user', 'case_collaborators',
                   ['user_id'])
    op.create_index('idx_case_collaborators_access', 'case_collaborators',
                   ['case_id', 'access_level'])

    op.create_index('idx_case_notes_case_created', 'case_notes',
                   ['case_id', 'created_at'])
    op.create_index('idx_case_notes_author', 'case_notes', ['author_id'])

    # Enable Row Level Security
    op.execute('ALTER TABLE patients ENABLE ROW LEVEL SECURITY;')
    op.execute('ALTER TABLE cases ENABLE ROW LEVEL SECURITY;')
    op.execute('ALTER TABLE case_collaborators ENABLE ROW LEVEL SECURITY;')
    op.execute('ALTER TABLE case_notes ENABLE ROW LEVEL SECURITY;')

    # Create RLS policies for organization isolation
    op.execute("""
        CREATE POLICY patient_org_isolation ON patients
        FOR ALL TO app_role
        USING (organization_id = current_setting('app.current_org_id', true)::uuid);
    """)

    op.execute("""
        CREATE POLICY case_org_isolation ON cases
        FOR ALL TO app_role
        USING (organization_id = current_setting('app.current_org_id', true)::uuid);
    """)

    # Complex RLS policy for case access based on assignment and collaboration
    op.execute("""
        CREATE POLICY case_access_control ON cases
        FOR ALL TO app_role
        USING (
            organization_id = current_setting('app.current_org_id', true)::uuid
            AND (
                assigned_user_id = current_setting('app.current_user_id', true)::uuid
                OR EXISTS (
                    SELECT 1 FROM case_collaborators cc
                    WHERE cc.case_id = cases.id
                    AND cc.user_id = current_setting('app.current_user_id', true)::uuid
                    AND cc.deleted_at IS NULL
                )
            )
        );
    """)

    op.execute("""
        CREATE POLICY case_collaborators_case_access ON case_collaborators
        FOR ALL TO app_role
        USING (
            EXISTS (
                SELECT 1 FROM cases c
                WHERE c.id = case_collaborators.case_id
                AND c.organization_id = current_setting('app.current_org_id', true)::uuid
            )
        );
    """)

    op.execute("""
        CREATE POLICY case_notes_case_access ON case_notes
        FOR ALL TO app_role
        USING (
            EXISTS (
                SELECT 1 FROM cases c
                WHERE c.id = case_notes.case_id
                AND c.organization_id = current_setting('app.current_org_id', true)::uuid
            )
            AND (
                NOT case_notes.is_private
                OR case_notes.author_id = current_setting('app.current_user_id', true)::uuid
            )
        );
    """)

    # Add updated_at triggers
    op.execute("""
        CREATE TRIGGER update_patients_updated_at
        BEFORE UPDATE ON patients
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    op.execute("""
        CREATE TRIGGER update_cases_updated_at
        BEFORE UPDATE ON cases
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    op.execute("""
        CREATE TRIGGER update_case_notes_updated_at
        BEFORE UPDATE ON case_notes
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # Create full-text search index for case content
    op.execute("""
        CREATE INDEX idx_cases_search
        ON cases
        USING gin(to_tsvector('english',
            coalesce(title, '') || ' ' ||
            coalesce(description, '') || ' ' ||
            coalesce(chief_complaint, '') || ' ' ||
            coalesce(history_present_illness, '')
        ));
    """)

    # Create function for case number generation
    op.execute("""
        CREATE OR REPLACE FUNCTION generate_case_number(org_id uuid)
        RETURNS text AS $$
        DECLARE
            year_prefix text := EXTRACT(YEAR FROM CURRENT_DATE)::text;
            sequence_num integer;
            case_number text;
        BEGIN
            -- Get next sequence number for the organization and year
            SELECT COALESCE(MAX(
                CASE
                    WHEN case_number ~ ('^' || year_prefix || '-[0-9]+$')
                    THEN substring(case_number from (length(year_prefix) + 2))::integer
                    ELSE 0
                END
            ), 0) + 1
            INTO sequence_num
            FROM cases
            WHERE organization_id = org_id
            AND case_number LIKE year_prefix || '-%';

            case_number := year_prefix || '-' || lpad(sequence_num::text, 6, '0');
            RETURN case_number;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    # Drop function
    op.execute('DROP FUNCTION IF EXISTS generate_case_number(uuid);')

    # Drop triggers
    op.execute('DROP TRIGGER IF EXISTS update_case_notes_updated_at ON case_notes;')
    op.execute('DROP TRIGGER IF EXISTS update_cases_updated_at ON cases;')
    op.execute('DROP TRIGGER IF EXISTS update_patients_updated_at ON patients;')

    # Drop RLS policies
    op.execute('DROP POLICY IF EXISTS case_notes_case_access ON case_notes;')
    op.execute('DROP POLICY IF EXISTS case_collaborators_case_access ON case_collaborators;')
    op.execute('DROP POLICY IF EXISTS case_access_control ON cases;')
    op.execute('DROP POLICY IF EXISTS case_org_isolation ON cases;')
    op.execute('DROP POLICY IF EXISTS patient_org_isolation ON patients;')

    # Drop tables
    op.drop_table('case_notes')
    op.drop_table('case_collaborators')
    op.drop_table('cases')
    op.drop_table('patients')

    # Drop custom types
    op.execute('DROP TYPE IF EXISTS gender;')
    op.execute('DROP TYPE IF EXISTS case_priority;')
    op.execute('DROP TYPE IF EXISTS case_status;')