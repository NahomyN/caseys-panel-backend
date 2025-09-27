"""Test daily statistics aggregation functionality."""
import pytest
from datetime import datetime, date, timezone
from app.services.database import SessionLocal
from app.services.models import WorkflowRun, RunNodeMetrics, DailyRunStats, WorkflowStatus
from app.services.analytics import recompute_daily_stats


def test_daily_stats_aggregation():
    """Test that daily statistics are correctly aggregated from runs and metrics."""
    db = SessionLocal()
    
    try:
        test_date = date(2024, 1, 15)
        test_date_str = test_date.strftime("%Y-%m-%d")
        
        # Clean up any existing data for this date
        db.query(DailyRunStats).filter_by(date=test_date_str).delete()
        db.query(RunNodeMetrics).filter(RunNodeMetrics.run_id.like("test_daily_%")).delete()
        db.query(WorkflowRun).filter(WorkflowRun.run_id.like("test_daily_%")).delete()
        db.commit()
        
        # Create test workflow runs
        run1 = WorkflowRun(
            run_id="test_daily_run1",
            patient_id="patient1",
            status=WorkflowStatus.COMPLETED,
            created_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        )
        run2 = WorkflowRun(
            run_id="test_daily_run2",
            patient_id="patient2",
            status=WorkflowStatus.FAILED,
            created_at=datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        )
        run3 = WorkflowRun(
            run_id="test_daily_run3",
            patient_id="patient3",
            status=WorkflowStatus.RUNNING,
            created_at=datetime(2024, 1, 15, 16, 45, 0, tzinfo=timezone.utc)
        )
        
        db.add_all([run1, run2, run3])
        db.commit()
        
        # Create test metrics
        metrics1 = RunNodeMetrics(
            run_id="test_daily_run1",
            node_key="agent_1",
            status="completed",
            success_duration_ms=1500,
            attempts=1,
            retries=0,
            fallback_used=0
        )
        metrics2 = RunNodeMetrics(
            run_id="test_daily_run2",
            node_key="agent_1",
            status="failed",
            failure_duration_ms=3000,
            attempts=2,
            retries=1,
            fallback_used=1
        )
        
        db.add_all([metrics1, metrics2])
        db.commit()
        
        # Run aggregation
        recompute_daily_stats(test_date, db)
        
        # Verify aggregated stats
        stats = db.query(DailyRunStats).filter_by(date=test_date_str).first()
        assert stats is not None
        assert stats.runs_started == 3
        assert stats.runs_completed == 1
        assert stats.failures == 1
        assert stats.fallbacks_used == 1
        assert stats.avg_total_duration_ms == 1500  # Only successful metrics counted
        
        print(f"✅ Daily stats aggregated: {stats.runs_started} started, {stats.runs_completed} completed")
        
    finally:
        # Cleanup
        db.query(DailyRunStats).filter_by(date=test_date_str).delete()
        db.query(RunNodeMetrics).filter(RunNodeMetrics.run_id.like("test_daily_%")).delete()
        db.query(WorkflowRun).filter(WorkflowRun.run_id.like("test_daily_%")).delete()
        db.commit()
        db.close()


def test_daily_stats_idempotent():
    """Test that recomputing stats for the same date is idempotent."""
    db = SessionLocal()
    
    try:
        test_date = date(2024, 2, 1)
        test_date_str = test_date.strftime("%Y-%m-%d")
        
        # Clean up
        db.query(DailyRunStats).filter_by(date=test_date_str).delete()
        db.query(RunNodeMetrics).filter(RunNodeMetrics.run_id.like("test_idem_%")).delete()
        db.query(WorkflowRun).filter(WorkflowRun.run_id.like("test_idem_%")).delete()
        db.commit()
        
        # Create single test run
        run = WorkflowRun(
            run_id="test_idem_run1",
            patient_id="patient_idem",
            status=WorkflowStatus.COMPLETED,
            created_at=datetime(2024, 2, 1, 12, 0, 0, tzinfo=timezone.utc)
        )
        db.add(run)
        db.commit()
        
        # First aggregation
        recompute_daily_stats(test_date, db)
        stats1 = db.query(DailyRunStats).filter_by(date=test_date_str).first()
        
        # Second aggregation (should update, not create duplicate)
        recompute_daily_stats(test_date, db)
        
        # Verify only one record exists
        all_stats = db.query(DailyRunStats).filter_by(date=test_date_str).all()
        assert len(all_stats) == 1
        assert all_stats[0].runs_started == 1
        
        print("✅ Daily stats recomputation is idempotent")
        
    finally:
        # Cleanup
        db.query(DailyRunStats).filter_by(date=test_date_str).delete()
        db.query(RunNodeMetrics).filter(RunNodeMetrics.run_id.like("test_idem_%")).delete()
        db.query(WorkflowRun).filter(WorkflowRun.run_id.like("test_idem_%")).delete()
        db.commit()
        db.close()


if __name__ == "__main__":
    test_daily_stats_aggregation()
    test_daily_stats_idempotent()