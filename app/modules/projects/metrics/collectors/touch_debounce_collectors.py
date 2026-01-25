# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/metrics/collectors/touch_debounce_collectors.py

Prometheus counters para observabilidad del touch_project_debounced.

Métricas expuestas (familias registradas en REGISTRY):
- touch_debounced_allowed_total{reason} - Touch ejecutado
- touch_debounced_skipped_total{reason} - Touch omitido por debounce
- touch_debounced_redis_error_total{reason} - Error de Redis (fail-open)
- touch_debounced_redis_unavailable_total{reason} - Redis no disponible

Las series con labels aparecen cuando hay actividad real.

Autor: DoxAI
Fecha: 2026-01-23
Updated: 2026-01-25 - exc_info=True for all errors
"""
from __future__ import annotations

import logging
from typing import Optional

from app.shared.core.metrics_helpers import get_or_create_counter

_logger = logging.getLogger("projects.touch_debounce.metrics")

# ---------------------------------------------------------------------------
# Counter names (Prometheus naming convention)
# ---------------------------------------------------------------------------
TOUCH_ALLOWED_COUNTER_NAME = "touch_debounced_allowed_total"
TOUCH_SKIPPED_COUNTER_NAME = "touch_debounced_skipped_total"
TOUCH_REDIS_ERROR_COUNTER_NAME = "touch_debounced_redis_error_total"
TOUCH_REDIS_UNAVAILABLE_COUNTER_NAME = "touch_debounced_redis_unavailable_total"

# ---------------------------------------------------------------------------
# Label names
# ---------------------------------------------------------------------------
LABEL_NAMES = ("reason",)


# ---------------------------------------------------------------------------
# Lazy initialization
# ---------------------------------------------------------------------------
_counters_initialized = False
_allowed_counter: Optional[object] = None
_skipped_counter: Optional[object] = None
_redis_error_counter: Optional[object] = None
_redis_unavailable_counter: Optional[object] = None


def _ensure_counters() -> bool:
    """
    Registra los counters en el REGISTRY de Prometheus.
    
    Después de esta llamada, /metrics mostrará # HELP y # TYPE para cada familia.
    Las series con labels aparecen cuando hay actividad real.
    
    Returns:
        True si los counters están registrados, False si hubo error.
    """
    global _counters_initialized
    global _allowed_counter, _skipped_counter
    global _redis_error_counter, _redis_unavailable_counter
    
    if _counters_initialized:
        return True
    
    try:
        _allowed_counter = get_or_create_counter(
            TOUCH_ALLOWED_COUNTER_NAME,
            "Touch project debounced - allowed (executed)",
            labelnames=LABEL_NAMES,
        )
        _skipped_counter = get_or_create_counter(
            TOUCH_SKIPPED_COUNTER_NAME,
            "Touch project debounced - skipped (debounce hit)",
            labelnames=LABEL_NAMES,
        )
        _redis_error_counter = get_or_create_counter(
            TOUCH_REDIS_ERROR_COUNTER_NAME,
            "Touch project debounced - Redis error (fail-open)",
            labelnames=LABEL_NAMES,
        )
        _redis_unavailable_counter = get_or_create_counter(
            TOUCH_REDIS_UNAVAILABLE_COUNTER_NAME,
            "Touch project debounced - Redis unavailable",
            labelnames=LABEL_NAMES,
        )
        
        _counters_initialized = True
        _logger.info("touch_debounce_metrics_registered: metrics=[%s, %s, %s, %s]",
                     TOUCH_ALLOWED_COUNTER_NAME, TOUCH_SKIPPED_COUNTER_NAME,
                     TOUCH_REDIS_ERROR_COUNTER_NAME, TOUCH_REDIS_UNAVAILABLE_COUNTER_NAME)
        return True
    except Exception as e:
        _logger.error(
            "touch_debounce_metrics_register_error: %s",
            str(e),
            exc_info=True,
        )
        return False


# ---------------------------------------------------------------------------
# Public API - Safe increment functions (no exceptions)
# ---------------------------------------------------------------------------
def inc_touch_allowed(reason: str = "unspecified") -> None:
    """Incrementa contador de touch permitido."""
    try:
        if _ensure_counters() and _allowed_counter:
            _allowed_counter.labels(reason=reason).inc()
    except Exception:
        pass


def inc_touch_skipped(reason: str = "unspecified") -> None:
    """Incrementa contador de touch omitido por debounce."""
    try:
        if _ensure_counters() and _skipped_counter:
            _skipped_counter.labels(reason=reason).inc()
    except Exception:
        pass


def inc_touch_redis_error(reason: str = "unspecified") -> None:
    """Incrementa contador de error Redis (fail-open activo)."""
    try:
        if _ensure_counters() and _redis_error_counter:
            _redis_error_counter.labels(reason=reason).inc()
    except Exception:
        pass


def inc_touch_redis_unavailable(reason: str = "unspecified") -> None:
    """Incrementa contador de Redis no disponible."""
    try:
        if _ensure_counters() and _redis_unavailable_counter:
            _redis_unavailable_counter.labels(reason=reason).inc()
    except Exception:
        pass


__all__ = [
    "inc_touch_allowed",
    "inc_touch_skipped",
    "inc_touch_redis_error",
    "inc_touch_redis_unavailable",
    "TOUCH_ALLOWED_COUNTER_NAME",
    "TOUCH_SKIPPED_COUNTER_NAME",
    "TOUCH_REDIS_ERROR_COUNTER_NAME",
    "TOUCH_REDIS_UNAVAILABLE_COUNTER_NAME",
    "_ensure_counters",
]
