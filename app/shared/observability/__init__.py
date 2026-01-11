# -*- coding: utf-8 -*-
"""
backend/app/shared/observability/__init__.py

Módulo de observabilidad: métricas HTTP, contadores, query timing, etc.
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

__all__ = [
    "HTTPMetricsMiddleware",
    "HttpMetricsStore",
    "RedisHttpMetricsStore",
    "DisabledHttpMetricsStore",
    "get_http_metrics_store",
    "reset_http_metrics_store",
    "QueryTimingContext",
    "timed_execute",
]
