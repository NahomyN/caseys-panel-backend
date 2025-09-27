"""Update EventType enum to canonical values

Revision ID: 002
Revises: 001
Create Date: 2025-08-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = '002b'
down_revision = '001'
branch_labels = None
depends_on = None

old_enum = sa.Enum('NODE_STARTED', 'NODE_PROGRESS', 'NODE_COMPLETED', 'NODE_FAILED', 'NODE_RETRIED', name='eventtype')
new_enum = sa.Enum('started', 'progress', 'completed', 'failed', 'retried', name='eventtype_new')


def upgrade():
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    if dialect_name == 'sqlite':
        # SQLite: enums are just TEXT; simpler approach: rename table and recreate
        op.rename_table('events', 'events_old_tmp')
        op.create_table(
            'events',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('run_id', sa.String(), nullable=False),
            sa.Column('node_key', sa.String(), nullable=False),
            sa.Column('event_type', sa.Enum('started','progress','completed','failed','retried', name='eventtype'), nullable=False),
            sa.Column('event_payload_json', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        )
        # copy data with mapping
        mapping_sql = """
            INSERT INTO events (id, run_id, node_key, event_type, event_payload_json, created_at)
            SELECT id, run_id, node_key,
                CASE event_type
                    WHEN 'NODE_STARTED' THEN 'started'
                    WHEN 'NODE_PROGRESS' THEN 'progress'
                    WHEN 'NODE_COMPLETED' THEN 'completed'
                    WHEN 'NODE_FAILED' THEN 'failed'
                    WHEN 'NODE_RETRIED' THEN 'retried'
                END as event_type,
                event_payload_json, created_at
            FROM events_old_tmp;
        """
        bind.execute(text(mapping_sql))
        op.drop_table('events_old_tmp')
    else:
        # Original Postgres-aware path
        new_enum.create(bind, checkfirst=True)
        op.add_column('events', sa.Column('event_type_new', new_enum, nullable=True))
        bind.execute(sa.text("""
            UPDATE events SET event_type_new = CASE event_type
                WHEN 'NODE_STARTED' THEN 'started'
                WHEN 'NODE_PROGRESS' THEN 'progress'
                WHEN 'NODE_COMPLETED' THEN 'completed'
                WHEN 'NODE_FAILED' THEN 'failed'
                WHEN 'NODE_RETRIED' THEN 'retried'
            END
        """))
        op.drop_column('events', 'event_type')
        op.alter_column('events', 'event_type_new', new_column_name='event_type')
        old_enum.drop(bind, checkfirst=True)
        op.execute("ALTER TYPE eventtype_new RENAME TO eventtype")


def downgrade():
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    if dialect_name == 'sqlite':
        # Best-effort: cannot restore original enum values cleanly; leave as-is
        pass
    else:
        old_enum.create(bind, checkfirst=True)
        op.add_column('events', sa.Column('event_type_old', old_enum, nullable=True))
        bind.execute(sa.text("""
            UPDATE events SET event_type_old = CASE event_type
                WHEN 'started' THEN 'NODE_STARTED'
                WHEN 'progress' THEN 'NODE_PROGRESS'
                WHEN 'completed' THEN 'NODE_COMPLETED'
                WHEN 'failed' THEN 'NODE_FAILED'
                WHEN 'retried' THEN 'NODE_RETRIED'
            END
        """))
        op.drop_column('events', 'event_type')
        op.alter_column('events', 'event_type_old', new_column_name='event_type')
        new_enum.drop(bind, checkfirst=True)
        op.execute("ALTER TYPE eventtype RENAME TO eventtype_old")
