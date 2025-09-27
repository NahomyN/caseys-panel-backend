"""Core Infrastructure - Organizations, Users, and RBAC

Revision ID: 010_core_infrastructure
Revises: dde00df6f577
Create Date: 2025-09-21 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '010_core_infrastructure'
down_revision = 'dde00df6f577'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable UUID extension
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')

    # Create custom types
    op.execute("""
        CREATE TYPE user_role AS ENUM (
            'admin',
            'attending',
            'resident',
            'nurse',
            'medical_student',
            'auditor'
        );
    """)

    op.execute("""
        CREATE TYPE access_level AS ENUM (
            'read',
            'write',
            'admin'
        );
    """)

    # Create organizations table
    op.create_table('organizations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                 server_default=sa.text('uuid_generate_v4()')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('address', sa.JSON),
        sa.Column('contact_info', sa.JSON),
        sa.Column('license_number', sa.String(100)),
        sa.Column('is_active', sa.Boolean, nullable=False, default=True),
        sa.Column('settings', sa.JSON, default={}),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # Create users table
    op.create_table('users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                 server_default=sa.text('uuid_generate_v4()')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('first_name', sa.String(100), nullable=False),
        sa.Column('last_name', sa.String(100), nullable=False),
        sa.Column('role', sa.Enum('admin', 'attending', 'resident', 'nurse',
                                 'medical_student', 'auditor', name='user_role'),
                 nullable=False),
        sa.Column('license_number', sa.String(100)),
        sa.Column('department', sa.String(100)),
        sa.Column('phone', sa.String(20)),
        sa.Column('is_active', sa.Boolean, nullable=False, default=True),
        sa.Column('last_login_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('preferences', sa.JSON, default={}),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # Create permissions table for fine-grained access control
    op.create_table('permissions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                 server_default=sa.text('uuid_generate_v4()')),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('description', sa.Text),
        sa.Column('resource_type', sa.String(50), nullable=False),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # Create role_permissions junction table
    op.create_table('role_permissions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                 server_default=sa.text('uuid_generate_v4()')),
        sa.Column('role', sa.Enum('admin', 'attending', 'resident', 'nurse',
                                 'medical_student', 'auditor', name='user_role'),
                 nullable=False),
        sa.Column('permission_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('permissions.id'), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('role', 'permission_id', 'organization_id',
                           name='unique_role_permission_org')
    )

    # Create audit_logs table for HIPAA compliance
    op.create_table('audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                 server_default=sa.text('uuid_generate_v4()')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                 sa.ForeignKey('users.id'), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('resource_type', sa.String(50), nullable=False),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True)),
        sa.Column('old_values', sa.JSON),
        sa.Column('new_values', sa.JSON),
        sa.Column('metadata', sa.JSON, default={}),
        sa.Column('ip_address', sa.String(45)),
        sa.Column('user_agent', sa.Text),
        sa.Column('session_id', sa.String(255)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # Create indexes for performance
    op.create_index('idx_organizations_active', 'organizations', ['is_active'])
    op.create_index('idx_users_organization_active', 'users',
                   ['organization_id', 'is_active'])
    op.create_index('idx_users_email', 'users', ['email'])
    op.create_index('idx_permissions_resource_action', 'permissions',
                   ['resource_type', 'action'])
    op.create_index('idx_audit_logs_org_created', 'audit_logs',
                   ['organization_id', 'created_at'])
    op.create_index('idx_audit_logs_user_created', 'audit_logs',
                   ['user_id', 'created_at'])
    op.create_index('idx_audit_logs_resource', 'audit_logs',
                   ['resource_type', 'resource_id'])

    # Insert default permissions
    op.execute("""
        INSERT INTO permissions (name, description, resource_type, action) VALUES
        ('read_patients', 'Read patient information', 'patient', 'read'),
        ('write_patients', 'Create and update patients', 'patient', 'write'),
        ('delete_patients', 'Delete patient records', 'patient', 'delete'),
        ('read_cases', 'Read case information', 'case', 'read'),
        ('write_cases', 'Create and update cases', 'case', 'write'),
        ('delete_cases', 'Delete cases', 'case', 'delete'),
        ('read_artifacts', 'Read artifacts and documents', 'artifact', 'read'),
        ('write_artifacts', 'Upload and update artifacts', 'artifact', 'write'),
        ('delete_artifacts', 'Delete artifacts', 'artifact', 'delete'),
        ('read_workflows', 'Read workflow information', 'workflow', 'read'),
        ('execute_workflows', 'Execute workflows', 'workflow', 'execute'),
        ('admin_workflows', 'Manage workflow definitions', 'workflow', 'admin'),
        ('read_audit_logs', 'Read audit logs', 'audit', 'read'),
        ('admin_users', 'Manage users and permissions', 'user', 'admin'),
        ('admin_organization', 'Manage organization settings', 'organization', 'admin');
    """)

    # Enable Row Level Security
    op.execute('ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;')
    op.execute('ALTER TABLE users ENABLE ROW LEVEL SECURITY;')
    op.execute('ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;')

    # Create RLS policies
    op.execute("""
        CREATE POLICY org_isolation ON organizations
        FOR ALL TO app_role
        USING (id = current_setting('app.current_org_id', true)::uuid);
    """)

    op.execute("""
        CREATE POLICY user_org_isolation ON users
        FOR ALL TO app_role
        USING (organization_id = current_setting('app.current_org_id', true)::uuid);
    """)

    op.execute("""
        CREATE POLICY audit_org_isolation ON audit_logs
        FOR ALL TO app_role
        USING (organization_id = current_setting('app.current_org_id', true)::uuid);
    """)

    # Create updated_at trigger function
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)

    # Add updated_at triggers
    op.execute("""
        CREATE TRIGGER update_organizations_updated_at
        BEFORE UPDATE ON organizations
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    op.execute("""
        CREATE TRIGGER update_users_updated_at
        BEFORE UPDATE ON users
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)


def downgrade() -> None:
    # Drop triggers
    op.execute('DROP TRIGGER IF EXISTS update_users_updated_at ON users;')
    op.execute('DROP TRIGGER IF EXISTS update_organizations_updated_at ON organizations;')
    op.execute('DROP FUNCTION IF EXISTS update_updated_at_column();')

    # Drop RLS policies
    op.execute('DROP POLICY IF EXISTS audit_org_isolation ON audit_logs;')
    op.execute('DROP POLICY IF EXISTS user_org_isolation ON users;')
    op.execute('DROP POLICY IF EXISTS org_isolation ON organizations;')

    # Drop tables
    op.drop_table('audit_logs')
    op.drop_table('role_permissions')
    op.drop_table('permissions')
    op.drop_table('users')
    op.drop_table('organizations')

    # Drop custom types
    op.execute('DROP TYPE IF EXISTS access_level;')
    op.execute('DROP TYPE IF EXISTS user_role;')