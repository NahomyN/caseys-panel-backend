"""Prometheus metrics instrumentation."""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response
from typing import Dict, Any


# Define metrics
runs_started_total = Counter(
    'runs_started_total',
    'Total number of workflow runs started'
)

runs_completed_total = Counter(
    'runs_completed_total',
    'Total number of workflow runs completed successfully',
    ['status']  # completed, failed
)

node_duration_ms = Histogram(
    'node_duration_ms',
    'Duration of node execution in milliseconds',
    ['node_key'],
    buckets=[50, 100, 250, 500, 1000, 2000, 5000, 10000, float('inf')]
)

# New enhanced metrics for better observability
workflow_duration_ms = Histogram(
    'workflow_duration_ms',
    'Total duration of workflow execution in milliseconds',
    ['status'],  # completed, failed
    buckets=[1000, 5000, 10000, 30000, 60000, 120000, 300000, float('inf')]
)

active_workflows = Gauge(
    'active_workflows',
    'Number of currently active/running workflows'
)

node_retries_total = Counter(
    'node_retries_total',
    'Total number of node retries',
    ['node_key']
)

model_usage_tokens_total = Counter(
    'model_usage_tokens_total',
    'Total number of tokens used by models',
    ['node_key', 'token_type', 'model']  # token_type: prompt, completion
)

_histogram_initialized = False

def _ensure_histogram_initialized():
    global _histogram_initialized
    if not _histogram_initialized:
        # Create a baseline label set so buckets appear even before any real observations
        node_duration_ms.labels(node_key="_init").observe(0.0)
        workflow_duration_ms.labels(status="_init").observe(0.0)
        _histogram_initialized = True

fallbacks_total = Counter(
    'fallbacks_total',
    'Total number of fallback switches',
    ['node_key']
)

safety_issues_total = Counter(
    'safety_issues_total',
    'Total number of safety issues detected',
    ['rule_id', 'severity']
)


def record_run_started():
    """Record a workflow run started."""
    runs_started_total.inc()
    active_workflows.inc()


def record_run_completed(status: str, duration_ms: float = None):
    """Record a workflow run completed."""
    runs_completed_total.labels(status=status).inc()
    active_workflows.dec()
    if duration_ms is not None:
        workflow_duration_ms.labels(status=status).observe(duration_ms)


def record_node_duration(node_key: str, duration_ms: float):
    """Record node execution duration."""
    node_duration_ms.labels(node_key=node_key).observe(duration_ms)


def record_node_retry(node_key: str):
    """Record a node retry."""
    node_retries_total.labels(node_key=node_key).inc()


def record_model_usage(node_key: str, model: str, prompt_tokens: int, completion_tokens: int):
    """Record model token usage."""
    model_usage_tokens_total.labels(node_key=node_key, token_type="prompt", model=model).inc(prompt_tokens)
    model_usage_tokens_total.labels(node_key=node_key, token_type="completion", model=model).inc(completion_tokens)


def record_fallback_used(node_key: str):
    """Record a fallback switch."""
    fallbacks_total.labels(node_key=node_key).inc()


def record_safety_issue(rule_id: str, severity: str):
    """Record a safety issue detection."""
    safety_issues_total.labels(rule_id=rule_id, severity=severity).inc()


def get_metrics_response() -> Response:
    """Get Prometheus metrics response."""
    _ensure_histogram_initialized()
    metrics_output = generate_latest()
    return Response(
        content=metrics_output,
        media_type=CONTENT_TYPE_LATEST
    )