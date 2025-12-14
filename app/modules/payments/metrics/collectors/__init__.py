
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/collectors/__init__.py

Colectores de métricas del módulo de pagos.

Autor: Ixchel Beristain
Fecha: 2025-12-13
"""

from .metrics_collector import MetricsCollector, get_metrics_collector
from .decorators import track_endpoint_metrics, track_payment_conversion
from .webhook_metrics import (
    WebhookMetricsCollector,
    WebhookMetrics,
    get_webhook_metrics,
    reset_webhook_metrics,
)

__all__ = [
    # Métricas generales
    "MetricsCollector",
    "get_metrics_collector",
    "track_endpoint_metrics",
    "track_payment_conversion",
    
    # Métricas de webhooks (FASE 3)
    "WebhookMetricsCollector",
    "WebhookMetrics",
    "get_webhook_metrics",
    "reset_webhook_metrics",
]

# Fin del archivo backend/app/modules/payments/metrics/collectors/__init__.py
