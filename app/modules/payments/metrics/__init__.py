
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/__init__.py

Sistema de métricas y monitoreo para pagos (estructura homologada con AUTH).

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

# Collector & helpers
from .collectors.metrics_collector import MetricsCollector, get_metrics_collector
from .collectors.decorators import track_endpoint_metrics, track_payment_conversion

# Schemas (snapshots básicos en memoria; KPIs históricos vendrán de MVs/aggregators)
from .schemas.metrics_schemas import (
    EndpointMetrics,
    ProviderConversionMetrics,
    MetricsSnapshot,
    MetricsSummary,
    HealthStatus,
    HealthAlert,
)

__all__ = [
    # Collector
    "MetricsCollector",
    "get_metrics_collector",

    # Decorators
    "track_endpoint_metrics",
    "track_payment_conversion",

    # Schemas
    "EndpointMetrics",
    "ProviderConversionMetrics",
    "MetricsSnapshot",
    "MetricsSummary",
    "HealthStatus",
    "HealthAlert",
]

# Fin del archivo backend\app\modules\payments\metrics\__init__.py
