# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/metrics/collectors/lifecycle_metrics.py

DEPRECATED: Este módulo está deprecado. Usar lifecycle_collectors.py en su lugar.

Este archivo existe solo para retrocompatibilidad con imports existentes.
Todas las funciones se reexportan desde lifecycle_collectors.py.

Autor: Ixchel Beristain
Fecha: 2026-01-28
"""
from __future__ import annotations

import warnings

# Re-export desde el nuevo módulo para retrocompatibilidad
from app.modules.projects.metrics.collectors.lifecycle_collectors import (
    record_lifecycle_metric,
    instrument_lifecycle_op,
    instrument_lifecycle,
    inc_lifecycle_request,
    observe_lifecycle_latency,
    _ensure_collectors,
    REQUESTS_TOTAL_NAME,
    LATENCY_NAME,
    LifecycleOp,
    Outcome,
)

# Deprecation warning en import
warnings.warn(
    "lifecycle_metrics is deprecated, use lifecycle_collectors instead",
    DeprecationWarning,
    stacklevel=2,
)


def get_lifecycle_metrics_summary() -> dict:
    """
    DEPRECATED: Esta función ya no es necesaria con el collector Prometheus.
    
    Retorna un dict vacío para retrocompatibilidad.
    Use /metrics para obtener métricas en formato Prometheus.
    """
    warnings.warn(
        "get_lifecycle_metrics_summary is deprecated, use /metrics endpoint",
        DeprecationWarning,
        stacklevel=2,
    )
    return {"requests": {}, "latency": {}}


__all__ = [
    "record_lifecycle_metric",
    "instrument_lifecycle_op",
    "instrument_lifecycle",
    "get_lifecycle_metrics_summary",
    "LifecycleOp",
    "Outcome",
]

# Fin del archivo
