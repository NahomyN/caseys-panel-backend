"""Analytics aggregation service (multi-tenant aware)."""
import os
from datetime import datetime, date, timezone, timedelta
from typing import Optional, Iterable
from sqlalchemy.orm import Session
from sqlalchemy import func
from .database import SessionLocal
from .models import WorkflowRun, RunNodeMetrics, DailyRunStats, WorkflowStatus


def recompute_daily_stats(target_date: Optional[date] = None, db: Optional[Session] = None, tenant_id: Optional[str] = None) -> None:
    """Recompute daily run statistics.

    If tenant_id provided, recompute only for that tenant. Otherwise recompute for all tenants
    with activity on that date.
    """
    if target_date is None:
        target_date = datetime.now(timezone.utc).date()

    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        date_str = target_date.strftime("%Y-%m-%d")
        tenants: Iterable[str]
        if tenant_id:
            tenants = [tenant_id]
        else:
            tenants = [t[0] for t in db.query(WorkflowRun.tenant_id).filter(
                func.date(WorkflowRun.created_at) == target_date
            ).distinct()]
            if not tenants:
                # Nothing to do
                return

        for t_id in tenants:
            runs_query = db.query(WorkflowRun).filter(
                func.date(WorkflowRun.created_at) == target_date,
                WorkflowRun.tenant_id == t_id
            )
            runs_started = runs_query.count()
            runs_completed = runs_query.filter(WorkflowRun.status == WorkflowStatus.COMPLETED).count()
            failures = runs_query.filter(WorkflowRun.status == WorkflowStatus.FAILED).count()

            metrics_query = db.query(RunNodeMetrics).join(WorkflowRun).filter(
                func.date(WorkflowRun.created_at) == target_date,
                WorkflowRun.tenant_id == t_id
            )
            successful_metrics = metrics_query.filter(RunNodeMetrics.success_duration_ms.isnot(None))
            avg_duration = db.query(func.avg(RunNodeMetrics.success_duration_ms)).filter(
                RunNodeMetrics.id.in_(successful_metrics.with_entities(RunNodeMetrics.id))
            ).scalar()
            fallbacks_used = metrics_query.filter(RunNodeMetrics.fallback_used == 1).count()

            existing_stat = db.query(DailyRunStats).filter_by(date=date_str, tenant_id=t_id).first()
            if existing_stat:
                existing_stat.runs_started = runs_started
                existing_stat.runs_completed = runs_completed
                existing_stat.avg_total_duration_ms = int(avg_duration) if avg_duration else None
                existing_stat.failures = failures
                existing_stat.fallbacks_used = fallbacks_used
            else:
                db.add(DailyRunStats(
                    date=date_str,
                    tenant_id=t_id,
                    runs_started=runs_started,
                    runs_completed=runs_completed,
                    avg_total_duration_ms=int(avg_duration) if avg_duration else None,
                    failures=failures,
                    fallbacks_used=fallbacks_used
                ))
        db.commit()
    finally:
        if close_db:
            db.close()


def trigger_daily_aggregation_if_prod():
    """Trigger daily aggregation for yesterday (all tenants) if in production."""
    if os.getenv("APP_ENV", "dev") == "prod":
        yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
        recompute_daily_stats(yesterday)