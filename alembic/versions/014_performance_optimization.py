"""Performance Optimization - Partitioning, Advanced Indexing, and Monitoring

Revision ID: 014_performance_optimization
Revises: 013_workflow_engine
Create Date: 2025-09-21 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '014_performance_optimization'
down_revision = '013_workflow_engine'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create partition maintenance functions
    op.execute("""
        CREATE OR REPLACE FUNCTION create_monthly_partition(
            table_name text,
            start_date date
        ) RETURNS void AS $$
        DECLARE
            partition_name text;
            end_date date;
        BEGIN
            partition_name := table_name || '_' || to_char(start_date, 'YYYY_MM');
            end_date := start_date + interval '1 month';

            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS %I PARTITION OF %I
                FOR VALUES FROM (%L) TO (%L)',
                partition_name, table_name, start_date, end_date
            );

            -- Create indexes on the partition
            EXECUTE format(
                'CREATE INDEX IF NOT EXISTS %I ON %I (organization_id, created_at)',
                partition_name || '_org_created_idx', partition_name
            );
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION create_weekly_partition(
            table_name text,
            start_date date
        ) RETURNS void AS $$
        DECLARE
            partition_name text;
            end_date date;
        BEGIN
            partition_name := table_name || '_' || to_char(start_date, 'YYYY_WW');
            end_date := start_date + interval '1 week';

            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS %I PARTITION OF %I
                FOR VALUES FROM (%L) TO (%L)',
                partition_name, table_name, start_date, end_date
            );

            -- Create indexes on the partition
            EXECUTE format(
                'CREATE INDEX IF NOT EXISTS %I ON %I (created_at)',
                partition_name || '_created_idx', partition_name
            );
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create partition management function
    op.execute("""
        CREATE OR REPLACE FUNCTION maintain_partitions() RETURNS void AS $$
        DECLARE
            current_month date;
            future_month date;
            current_week date;
            future_week date;
        BEGIN
            -- Maintain monthly partitions for artifacts (6 months ahead)
            current_month := date_trunc('month', CURRENT_DATE);
            FOR i IN 0..6 LOOP
                future_month := current_month + (i || ' months')::interval;
                PERFORM create_monthly_partition('artifacts', future_month);
            END LOOP;

            -- Maintain weekly partitions for audit_logs (8 weeks ahead)
            current_week := date_trunc('week', CURRENT_DATE);
            FOR i IN 0..8 LOOP
                future_week := current_week + (i || ' weeks')::interval;
                PERFORM create_weekly_partition('audit_logs', future_week);
            END LOOP;

            -- Maintain weekly partitions for artifact_access_log (8 weeks ahead)
            FOR i IN 0..8 LOOP
                future_week := current_week + (i || ' weeks')::interval;
                PERFORM create_weekly_partition('artifact_access_log', future_week);
            END LOOP;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Convert large tables to partitioned tables
    # Note: In production, this would need to be done carefully with downtime
    # For now, we'll create the partition structure for new data

    # Create performance monitoring tables
    op.create_table('query_performance_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                 server_default=sa.text('uuid_generate_v4()')),
        sa.Column('query_hash', sa.String(64), nullable=False),
        sa.Column('query_text', sa.Text),
        sa.Column('execution_time_ms', sa.Float, nullable=False),
        sa.Column('rows_examined', sa.BigInteger),
        sa.Column('rows_returned', sa.BigInteger),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True)),
        sa.Column('user_id', postgresql.UUID(as_uuid=True)),
        sa.Column('endpoint', sa.String(255)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP'))
    )

    op.create_table('index_usage_stats',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                 server_default=sa.text('uuid_generate_v4()')),
        sa.Column('schema_name', sa.String(100), nullable=False),
        sa.Column('table_name', sa.String(100), nullable=False),
        sa.Column('index_name', sa.String(100), nullable=False),
        sa.Column('index_scans', sa.BigInteger, default=0),
        sa.Column('tuples_read', sa.BigInteger, default=0),
        sa.Column('tuples_fetched', sa.BigInteger, default=0),
        sa.Column('size_bytes', sa.BigInteger),
        sa.Column('last_scan', sa.TIMESTAMP(timezone=True)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                 server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('schema_name', 'table_name', 'index_name',
                           name='unique_index_stats')
    )

    # Create advanced composite indexes for common query patterns
    op.execute("""
        -- Composite index for case search by organization, status, and date
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cases_org_status_created_advanced
        ON cases (organization_id, status, created_at DESC)
        WHERE deleted_at IS NULL;
    """)

    op.execute("""
        -- Composite index for artifact search by case and type
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_artifacts_case_type_created
        ON artifacts (case_id, artifact_type_id, created_at DESC)
        WHERE status = 'active';
    """)

    op.execute("""
        -- Composite index for workflow runs by organization and status
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_workflow_runs_org_status_priority
        ON workflow_runs (organization_id, status, priority DESC, created_at DESC);
    """)

    op.execute("""
        -- Composite index for user access patterns
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_org_role_active
        ON users (organization_id, role, is_active)
        WHERE deleted_at IS NULL;
    """)

    op.execute("""
        -- Partial index for active cases assigned to users
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cases_assigned_active
        ON cases (assigned_user_id, status, updated_at DESC)
        WHERE status IN ('active', 'pending_review') AND deleted_at IS NULL;
    """)

    op.execute("""
        -- Composite index for case collaborators
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_case_collaborators_user_access
        ON case_collaborators (user_id, access_level, case_id)
        WHERE deleted_at IS NULL;
    """)

    # Create BRIN indexes for time-series data (efficient for large tables)
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_logs_created_brin
        ON audit_logs USING brin (created_at);
    """)

    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_artifact_access_log_created_brin
        ON artifact_access_log USING brin (created_at);
    """)

    # Create indexes on JSON fields for specific use cases
    op.execute("""
        -- Index on patient medical history for common lookups
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_patients_medical_history_allergies
        ON patients USING gin ((medical_history->'allergies'));
    """)

    op.execute("""
        -- Index on case differential diagnosis
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cases_differential_diagnosis
        ON cases USING gin (differential_diagnosis);
    """)

    op.execute("""
        -- Index on workflow definition for searching
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_workflows_definition_triggers
        ON workflows USING gin (definition, triggers);
    """)

    # Create materialized view for dashboard analytics
    op.execute("""
        CREATE MATERIALIZED VIEW dashboard_analytics AS
        SELECT
            o.id as organization_id,
            o.name as organization_name,
            COUNT(DISTINCT u.id) FILTER (WHERE u.is_active = true) as active_users,
            COUNT(DISTINCT p.id) FILTER (WHERE p.is_active = true) as active_patients,
            COUNT(DISTINCT c.id) FILTER (WHERE c.status = 'active') as active_cases,
            COUNT(DISTINCT c.id) FILTER (WHERE c.status = 'completed' AND c.updated_at >= CURRENT_DATE - INTERVAL '30 days') as completed_cases_30d,
            COUNT(DISTINCT a.id) FILTER (WHERE a.status = 'active') as total_artifacts,
            COUNT(DISTINCT wr.id) FILTER (WHERE wr.status = 'running') as running_workflows,
            COUNT(DISTINCT wr.id) FILTER (WHERE wr.status = 'completed' AND wr.completed_at >= CURRENT_DATE - INTERVAL '7 days') as completed_workflows_7d,
            AVG(wr.duration_seconds) FILTER (WHERE wr.status = 'completed' AND wr.completed_at >= CURRENT_DATE - INTERVAL '30 days') as avg_workflow_duration_30d,
            COUNT(DISTINCT al.id) FILTER (WHERE al.created_at >= CURRENT_DATE - INTERVAL '24 hours') as audit_events_24h,
            CURRENT_TIMESTAMP as last_updated
        FROM organizations o
        LEFT JOIN users u ON o.id = u.organization_id AND u.deleted_at IS NULL
        LEFT JOIN patients p ON o.id = p.organization_id AND p.deleted_at IS NULL
        LEFT JOIN cases c ON o.id = c.organization_id AND c.deleted_at IS NULL
        LEFT JOIN artifacts a ON o.id = a.organization_id AND a.deleted_at IS NULL
        LEFT JOIN workflow_runs wr ON o.id = wr.organization_id
        LEFT JOIN audit_logs al ON o.id = al.organization_id
        WHERE o.is_active = true AND o.deleted_at IS NULL
        GROUP BY o.id, o.name;
    """)

    # Create unique index on materialized view
    op.execute("""
        CREATE UNIQUE INDEX idx_dashboard_analytics_org_id
        ON dashboard_analytics (organization_id);
    """)

    # Create function to refresh materialized view
    op.execute("""
        CREATE OR REPLACE FUNCTION refresh_dashboard_analytics()
        RETURNS void AS $$
        BEGIN
            REFRESH MATERIALIZED VIEW CONCURRENTLY dashboard_analytics;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create performance monitoring functions
    op.execute("""
        CREATE OR REPLACE FUNCTION log_slow_query(
            p_query_hash text,
            p_query_text text,
            p_execution_time_ms float,
            p_rows_examined bigint DEFAULT NULL,
            p_rows_returned bigint DEFAULT NULL,
            p_organization_id uuid DEFAULT NULL,
            p_user_id uuid DEFAULT NULL,
            p_endpoint text DEFAULT NULL
        ) RETURNS void AS $$
        BEGIN
            INSERT INTO query_performance_log (
                query_hash, query_text, execution_time_ms, rows_examined,
                rows_returned, organization_id, user_id, endpoint
            ) VALUES (
                p_query_hash, p_query_text, p_execution_time_ms, p_rows_examined,
                p_rows_returned, p_organization_id, p_user_id, p_endpoint
            );
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION update_index_usage_stats()
        RETURNS void AS $$
        BEGIN
            INSERT INTO index_usage_stats (
                schema_name, table_name, index_name, index_scans,
                tuples_read, tuples_fetched, size_bytes, last_scan
            )
            SELECT
                schemaname,
                tablename,
                indexname,
                idx_scan,
                idx_tup_read,
                idx_tup_fetch,
                pg_relation_size(indexrelid),
                CASE WHEN idx_scan > 0 THEN CURRENT_TIMESTAMP END
            FROM pg_stat_user_indexes
            WHERE schemaname = 'public'
            ON CONFLICT (schema_name, table_name, index_name)
            DO UPDATE SET
                index_scans = EXCLUDED.index_scans,
                tuples_read = EXCLUDED.tuples_read,
                tuples_fetched = EXCLUDED.tuples_fetched,
                size_bytes = EXCLUDED.size_bytes,
                last_scan = EXCLUDED.last_scan,
                updated_at = CURRENT_TIMESTAMP;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create function for database health check
    op.execute("""
        CREATE OR REPLACE FUNCTION database_health_check()
        RETURNS json AS $$
        DECLARE
            result json;
            total_size bigint;
            table_count int;
            index_count int;
            connection_count int;
            slow_queries int;
            unused_indexes int;
        BEGIN
            -- Get database size
            SELECT pg_database_size(current_database()) INTO total_size;

            -- Get table and index counts
            SELECT count(*) FROM information_schema.tables
            WHERE table_schema = 'public' INTO table_count;

            SELECT count(*) FROM pg_indexes
            WHERE schemaname = 'public' INTO index_count;

            -- Get connection count
            SELECT count(*) FROM pg_stat_activity
            WHERE datname = current_database() INTO connection_count;

            -- Get slow queries in last hour
            SELECT count(*) FROM query_performance_log
            WHERE execution_time_ms > 1000
            AND created_at >= CURRENT_TIMESTAMP - INTERVAL '1 hour' INTO slow_queries;

            -- Get unused indexes
            SELECT count(*) FROM index_usage_stats
            WHERE index_scans = 0
            AND created_at < CURRENT_TIMESTAMP - INTERVAL '7 days' INTO unused_indexes;

            result := json_build_object(
                'database_size_bytes', total_size,
                'database_size_mb', round(total_size / 1024.0 / 1024.0, 2),
                'table_count', table_count,
                'index_count', index_count,
                'active_connections', connection_count,
                'slow_queries_last_hour', slow_queries,
                'unused_indexes', unused_indexes,
                'timestamp', CURRENT_TIMESTAMP
            );

            RETURN result;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create indexes on performance monitoring tables
    op.create_index('idx_query_performance_log_hash_created', 'query_performance_log',
                   ['query_hash', 'created_at'])
    op.create_index('idx_query_performance_log_execution_time', 'query_performance_log',
                   ['execution_time_ms'])
    op.create_index('idx_query_performance_log_org_created', 'query_performance_log',
                   ['organization_id', 'created_at'])

    op.create_index('idx_index_usage_stats_scans', 'index_usage_stats',
                   ['index_scans'])
    op.create_index('idx_index_usage_stats_last_scan', 'index_usage_stats',
                   ['last_scan'])

    # Add updated_at trigger to index_usage_stats
    op.execute("""
        CREATE TRIGGER update_index_usage_stats_updated_at
        BEFORE UPDATE ON index_usage_stats
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # Create function for cleanup of old performance data
    op.execute("""
        CREATE OR REPLACE FUNCTION cleanup_performance_data()
        RETURNS void AS $$
        BEGIN
            -- Keep only 30 days of query performance logs
            DELETE FROM query_performance_log
            WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '30 days';

            -- Update index usage stats
            PERFORM update_index_usage_stats();

            -- Refresh dashboard analytics
            PERFORM refresh_dashboard_analytics();

            -- Log cleanup activity
            INSERT INTO audit_logs (
                organization_id, action, resource_type, metadata, created_at
            ) VALUES (
                NULL,
                'performance_data_cleanup',
                'system',
                json_build_object(
                    'query_logs_cleaned', true,
                    'index_stats_updated', true,
                    'dashboard_refreshed', true
                ),
                CURRENT_TIMESTAMP
            );
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Run initial partition maintenance
    op.execute('SELECT maintain_partitions();')

    # Run initial performance data collection
    op.execute('SELECT update_index_usage_stats();')
    op.execute('SELECT refresh_dashboard_analytics();')


def downgrade() -> None:
    # Drop functions
    op.execute('DROP FUNCTION IF EXISTS cleanup_performance_data();')
    op.execute('DROP FUNCTION IF EXISTS database_health_check();')
    op.execute('DROP FUNCTION IF EXISTS update_index_usage_stats();')
    op.execute('DROP FUNCTION IF EXISTS log_slow_query(text, text, float, bigint, bigint, uuid, uuid, text);')
    op.execute('DROP FUNCTION IF EXISTS refresh_dashboard_analytics();')
    op.execute('DROP FUNCTION IF EXISTS maintain_partitions();')
    op.execute('DROP FUNCTION IF EXISTS create_weekly_partition(text, date);')
    op.execute('DROP FUNCTION IF EXISTS create_monthly_partition(text, date);')

    # Drop materialized view
    op.execute('DROP MATERIALIZED VIEW IF EXISTS dashboard_analytics;')

    # Drop performance monitoring tables
    op.drop_table('index_usage_stats')
    op.drop_table('query_performance_log')

    # Note: In a real downgrade, we would also drop the indexes created
    # but since they were created with IF NOT EXISTS, we'll leave them
    # for safety in this example