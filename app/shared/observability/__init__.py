# -*- coding: utf-8 -*-
"""
backend/app/shared/observability/__init__.py

Módulo de observabilidad: métricas HTTP, contadores, query timing, timed routes, job tracking,
y DB-to-Prometheus exporter.
"""
from .http_metrics_middleware import HTTPMetricsMiddleware
from .http_metrics_store import (
    HttpMetricsStore,
    get_http_metrics_store,
    reset_http_metrics_store,
)
from .redis_http_metrics_store import (
    RedisHttpMetricsStore,
    DisabledHttpMetricsStore,
)
from .query_timing import QueryTimingContext, timed_execute
from .timed_route import TimedAPIRoute
from .job_execution_tracker import JobExecutionTracker, track_job_execution
from .db_metrics_collector import (
    DBMetricsCollector,
    get_db_metrics_collector,
    refresh_db_metrics_if_needed,
    GHOST_FILES_COUNT_NAME,
    JOBS_FAILED_24H_NAME,
    JOBS_CRITICAL_STATUS_NAME,
    STORAGE_DELTA_NAME,
    CRITICAL_JOBS,
)

__all__ = [
    "HTTPMetricsMiddleware",
    "HttpMetricsStore",
    "RedisHttpMetricsStore",
    "DisabledHttpMetricsStore",
    "get_http_metrics_store",
    "reset_http_metrics_store",
    "QueryTimingContext",
    "timed_execute",
    "TimedAPIRoute",
    "JobExecutionTracker",
    "track_job_execution",
    # DB-to-Prometheus exporter
    "DBMetricsCollector",
    "get_db_metrics_collector",
    "refresh_db_metrics_if_needed",
    "GHOST_FILES_COUNT_NAME",
    "JOBS_FAILED_24H_NAME",
    "JOBS_CRITICAL_STATUS_NAME",
    "STORAGE_DELTA_NAME",
    "CRITICAL_JOBS",
]
