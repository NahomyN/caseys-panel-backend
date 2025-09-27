"""Artifact Management - Documents, Images, and File Storage

Revision ID: 012_artifact_management
Revises: 011_clinical_data
Create Date: 2025-09-21 20:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '012_artifact_management'
down_revision = '011_clinical_data'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create custom types for artifact management
    op.execute("""
        CREATE TYPE artifact_type AS ENUM (
            'document',
            'image',
            'video',
            'audio',
            'lab_result',
            'imaging_study',
            'pathology_report',
            'medication_list',
            'discharge_summary',
            'operative_note',
            'consultation_note',
            'progress_note',
            'other'
        );
    """)

    op.execute("""
        CREATE TYPE artifact_status AS ENUM (
            'uploading',
            'processing',
            'active',
            'archived',
            'quarantined',
            'deleted'
        );
    """)

    op.execute("""
        CREATE TYPE privacy_level AS ENUM (
            'public',
            'internal',
            'confidential',
            'restricted'
        );
    """)

    # Create artifact_types table for classification
    op.create_table('artifact_types',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                 server_default=sa.text('uuid_generate_v4()')),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('description', sa.Text),
        sa.Column('category', sa.Enum('document', 'image', 'video', 'audio',
                                     'lab_result', 'imaging_study', 'pathology_report',
                                     'medication_list', 'discharge_summary',
                                     'operative_note', 'consultation_note',
                                     'progress_note', 'other', name='artifact_type'),
                 nullable=False),
        sa.Column('mime_types', sa.ARRAY(sa.String(100)), default=[]),
        sa.Column('max_file_size', sa.BigInteger),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('validation_rules', sa.JSON, default={}),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP'))
    )

    # Create artifacts table (partitioned by created_at for scalability)
    op.create_table('artifacts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                 server_default=sa.text('uuid_generate_v4()')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('case_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('cases.id'), nullable=False),
        sa.Column('patient_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('uploaded_by', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('users.id'), nullable=False),
        sa.Column('artifact_type_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('artifact_types.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('file_size', sa.BigInteger, nullable=False),
        sa.Column('mime_type', sa.String(100), nullable=False),
        sa.Column('file_hash', sa.String(128), nullable=False),  # SHA-256
        sa.Column('status', sa.Enum('uploading', 'processing', 'active',
                                   'archived', 'quarantined', 'deleted',
                                   name='artifact_status'), nullable=False, default='uploading'),
        sa.Column('privacy_level', sa.Enum('public', 'internal', 'confidential',
                                          'restricted', name='privacy_level'),
                 nullable=False, default='internal'),
        sa.Column('content', sa.Text),  # Extracted text content for search
        sa.Column('metadata', sa.JSON, default={}),
        sa.Column('analysis_results', sa.JSON, default={}),  # AI analysis results
        sa.Column('tags', sa.ARRAY(sa.String(50)), default=[]),
        sa.Column('version', sa.Integer, default=1),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('artifacts.id'), nullable=True),  # For versioning
        sa.Column('retention_date', sa.TIMESTAMP(timezone=True)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True), nullable=True)
    )

    # Create artifact_access_log for detailed audit trail
    op.create_table('artifact_access_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                 server_default=sa.text('uuid_generate_v4()')),
        sa.Column('artifact_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('artifacts.id'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('users.id'), nullable=False),
        sa.Column('action', sa.String(50), nullable=False),  # view, download, edit, delete
        sa.Column('ip_address', sa.String(45)),
        sa.Column('user_agent', sa.Text),
        sa.Column('session_id', sa.String(255)),
        sa.Column('metadata', sa.JSON, default={}),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP'))
    )

    # Create artifact_annotations for AI and human annotations
    op.create_table('artifact_annotations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                 server_default=sa.text('uuid_generate_v4()')),
        sa.Column('artifact_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('artifacts.id'), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('users.id'), nullable=True),  # NULL for AI annotations
        sa.Column('annotation_type', sa.String(50), nullable=False),
        sa.Column('coordinates', sa.JSON),  # For position-based annotations
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('confidence_score', sa.Float),  # For AI annotations
        sa.Column('is_verified', sa.Boolean, default=False),
        sa.Column('verified_by', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('users.id'), nullable=True),
        sa.Column('metadata', sa.JSON, default={}),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP'))
    )

    # Create indexes for performance
    op.create_index('idx_artifact_types_category', 'artifact_types', ['category'])
    op.create_index('idx_artifact_types_active', 'artifact_types', ['is_active'])

    op.create_index('idx_artifacts_org_case', 'artifacts',
                   ['organization_id', 'case_id'])
    op.create_index('idx_artifacts_patient', 'artifacts', ['patient_id'])
    op.create_index('idx_artifacts_uploaded_by', 'artifacts', ['uploaded_by'])
    op.create_index('idx_artifacts_type', 'artifacts', ['artifact_type_id'])
    op.create_index('idx_artifacts_status', 'artifacts', ['status'])
    op.create_index('idx_artifacts_created', 'artifacts', ['created_at'])
    op.create_index('idx_artifacts_hash', 'artifacts', ['file_hash'])
    op.create_index('idx_artifacts_tags', 'artifacts', ['tags'], postgresql_using='gin')
    op.create_index('idx_artifacts_parent', 'artifacts', ['parent_id'])

    op.create_index('idx_artifact_access_log_artifact_created', 'artifact_access_log',
                   ['artifact_id', 'created_at'])
    op.create_index('idx_artifact_access_log_user', 'artifact_access_log',
                   ['user_id'])

    op.create_index('idx_artifact_annotations_artifact', 'artifact_annotations',
                   ['artifact_id'])
    op.create_index('idx_artifact_annotations_type', 'artifact_annotations',
                   ['annotation_type'])
    op.create_index('idx_artifact_annotations_created_by', 'artifact_annotations',
                   ['created_by'])

    # Create full-text search index for artifact content
    op.execute("""
        CREATE INDEX idx_artifacts_content_search
        ON artifacts
        USING gin(to_tsvector('english',
            coalesce(name, '') || ' ' ||
            coalesce(description, '') || ' ' ||
            coalesce(content, '')
        ));
    """)

    # Enable Row Level Security
    op.execute('ALTER TABLE artifacts ENABLE ROW LEVEL SECURITY;')
    op.execute('ALTER TABLE artifact_access_log ENABLE ROW LEVEL SECURITY;')
    op.execute('ALTER TABLE artifact_annotations ENABLE ROW LEVEL SECURITY;')

    # Create RLS policies
    op.execute("""
        CREATE POLICY artifact_org_isolation ON artifacts
        FOR ALL TO app_role
        USING (organization_id = current_setting('app.current_org_id', true)::uuid);
    """)

    op.execute("""
        CREATE POLICY artifact_access_case_based ON artifacts
        FOR ALL TO app_role
        USING (
            organization_id = current_setting('app.current_org_id', true)::uuid
            AND EXISTS (
                SELECT 1 FROM cases c
                WHERE c.id = artifacts.case_id
                AND (
                    c.assigned_user_id = current_setting('app.current_user_id', true)::uuid
                    OR EXISTS (
                        SELECT 1 FROM case_collaborators cc
                        WHERE cc.case_id = c.id
                        AND cc.user_id = current_setting('app.current_user_id', true)::uuid
                        AND cc.deleted_at IS NULL
                    )
                )
            )
        );
    """)

    op.execute("""
        CREATE POLICY artifact_access_log_artifact_access ON artifact_access_log
        FOR ALL TO app_role
        USING (
            EXISTS (
                SELECT 1 FROM artifacts a
                WHERE a.id = artifact_access_log.artifact_id
                AND a.organization_id = current_setting('app.current_org_id', true)::uuid
            )
        );
    """)

    op.execute("""
        CREATE POLICY artifact_annotations_artifact_access ON artifact_annotations
        FOR ALL TO app_role
        USING (
            EXISTS (
                SELECT 1 FROM artifacts a
                WHERE a.id = artifact_annotations.artifact_id
                AND a.organization_id = current_setting('app.current_org_id', true)::uuid
            )
        );
    """)

    # Add updated_at triggers
    op.execute("""
        CREATE TRIGGER update_artifact_types_updated_at
        BEFORE UPDATE ON artifact_types
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    op.execute("""
        CREATE TRIGGER update_artifacts_updated_at
        BEFORE UPDATE ON artifacts
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    op.execute("""
        CREATE TRIGGER update_artifact_annotations_updated_at
        BEFORE UPDATE ON artifact_annotations
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # Insert default artifact types
    op.execute("""
        INSERT INTO artifact_types (name, description, category, mime_types, max_file_size) VALUES
        ('PDF Document', 'General PDF documents', 'document', ARRAY['application/pdf'], 52428800),
        ('Word Document', 'Microsoft Word documents', 'document', ARRAY['application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'], 52428800),
        ('Medical Image', 'Medical imaging files', 'image', ARRAY['image/jpeg', 'image/png', 'image/tiff'], 104857600),
        ('DICOM Image', 'DICOM medical images', 'imaging_study', ARRAY['application/dicom'], 524288000),
        ('Lab Result PDF', 'Laboratory test results', 'lab_result', ARRAY['application/pdf'], 10485760),
        ('Pathology Report', 'Pathology examination reports', 'pathology_report', ARRAY['application/pdf', 'text/plain'], 10485760),
        ('Medication List', 'Patient medication lists', 'medication_list', ARRAY['application/pdf', 'text/plain', 'text/csv'], 5242880),
        ('Discharge Summary', 'Patient discharge summaries', 'discharge_summary', ARRAY['application/pdf', 'text/plain'], 10485760),
        ('Operative Note', 'Surgical operative notes', 'operative_note', ARRAY['application/pdf', 'text/plain'], 10485760),
        ('Consultation Note', 'Specialist consultation notes', 'consultation_note', ARRAY['application/pdf', 'text/plain'], 10485760),
        ('Progress Note', 'Patient progress notes', 'progress_note', ARRAY['application/pdf', 'text/plain'], 5242880);
    """)

    # Create function for file retention management
    op.execute("""
        CREATE OR REPLACE FUNCTION cleanup_expired_artifacts()
        RETURNS void AS $$
        BEGIN
            -- Archive artifacts past retention date
            UPDATE artifacts
            SET status = 'archived'
            WHERE retention_date < CURRENT_TIMESTAMP
            AND status = 'active';

            -- Log cleanup activity
            INSERT INTO audit_logs (
                organization_id, action, resource_type, metadata, created_at
            )
            SELECT DISTINCT
                organization_id,
                'artifact_retention_cleanup',
                'artifact',
                jsonb_build_object('count', COUNT(*)),
                CURRENT_TIMESTAMP
            FROM artifacts
            WHERE status = 'archived'
            AND updated_at > CURRENT_TIMESTAMP - INTERVAL '1 day'
            GROUP BY organization_id;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    # Drop function
    op.execute('DROP FUNCTION IF EXISTS cleanup_expired_artifacts();')

    # Drop triggers
    op.execute('DROP TRIGGER IF EXISTS update_artifact_annotations_updated_at ON artifact_annotations;')
    op.execute('DROP TRIGGER IF EXISTS update_artifacts_updated_at ON artifacts;')
    op.execute('DROP TRIGGER IF EXISTS update_artifact_types_updated_at ON artifact_types;')

    # Drop RLS policies
    op.execute('DROP POLICY IF EXISTS artifact_annotations_artifact_access ON artifact_annotations;')
    op.execute('DROP POLICY IF EXISTS artifact_access_log_artifact_access ON artifact_access_log;')
    op.execute('DROP POLICY IF EXISTS artifact_access_case_based ON artifacts;')
    op.execute('DROP POLICY IF EXISTS artifact_org_isolation ON artifacts;')

    # Drop tables
    op.drop_table('artifact_annotations')
    op.drop_table('artifact_access_log')
    op.drop_table('artifacts')
    op.drop_table('artifact_types')

    # Drop custom types
    op.execute('DROP TYPE IF EXISTS privacy_level;')
    op.execute('DROP TYPE IF EXISTS artifact_status;')
    op.execute('DROP TYPE IF EXISTS artifact_type;')