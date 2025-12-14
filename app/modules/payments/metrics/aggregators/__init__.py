
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/aggregators/__init__.py

Re-exporta tipos del subpaquete `storage` para un import limpio:
    from app.modules.payments.metrics.aggregators import MetricsStorage, TimeWindow, ...

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

from .storage.time_window import TimeWindow
from .storage.latency_bucket import LatencyBucket
from .storage.conversion_bucket import ConversionBucket
from .storage.storage_core import MetricsStorage

__all__ = [
    "TimeWindow",
    "LatencyBucket",
    "ConversionBucket",
    "MetricsStorage",
]

# Fin del archivo backend\app\modules\payments\metrics\aggregators\__init__.py