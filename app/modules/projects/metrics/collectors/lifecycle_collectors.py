# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/metrics/collectors/lifecycle_collectors.py

Prometheus collectors para operaciones lifecycle de proyectos.

Métricas expuestas (familias registradas en REGISTRY):
- projects_lifecycle_requests_total{op,outcome} - Contador de operaciones
- projects_lifecycle_latency_seconds{op,outcome} - Histogram de latencia

Labels:
- op: create | update | close | hard_delete
- outcome: success | error

🚫 Prohibido: project_id, auth_user_id (alta cardinalidad)

Autor: Ixchel Beristain
Fecha: 2026-01-28
"""
from __future__ import annotations

import logging
import time
from typing import Literal, Optional
from contextlib import asynccontextmanager

from app.shared.core.metrics_helpers import (
    get_or_create_counter,
    get_or_create_histogram,
)

_logger = logging.getLogger("projects.lifecycle.metrics")

# ---------------------------------------------------------------------------
# Tipos y constantes
# ---------------------------------------------------------------------------
LifecycleOp = Literal["create", "update", "close", "hard_delete"]
Outcome = Literal["success", "error"]

# ---------------------------------------------------------------------------
# Metric names (Prometheus naming convention)
# ---------------------------------------------------------------------------
REQUESTS_TOTAL_NAME = "projects_lifecycle_requests_total"
LATENCY_NAME = "projects_lifecycle_latency_seconds"

# ---------------------------------------------------------------------------
# Label names
# ---------------------------------------------------------------------------
LABELS = ("op", "outcome")

# ---------------------------------------------------------------------------
# Default histogram buckets (seconds)
# ---------------------------------------------------------------------------
LATENCY_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, float("inf"))

# ---------------------------------------------------------------------------
# Lazy initialization
# ---------------------------------------------------------------------------
_collectors_initialized = False
_requests_total: Optional[object] = None
_latency: Optional[object] = None


def _ensure_collectors() -> bool:
    """
    Registra los collectors en el REGISTRY de Prometheus.
    
    Después de esta llamada, /metrics mostrará # HELP y # TYPE para cada familia.
    Las series con labels aparecen cuando hay actividad real.
    
    Returns:
        True si los collectors están registrados, False si hubo error.
    """
    global _collectors_initialized
    global _requests_total, _latency
    
    if _collectors_initialized:
        return True
    
    try:
        _requests_total = get_or_create_counter(
            REQUESTS_TOTAL_NAME,
            "Total project lifecycle operations",
            labelnames=LABELS,
        )
        _latency = get_or_create_histogram(
            LATENCY_NAME,
            "Latency of project lifecycle operations in seconds",
            labelnames=LABELS,
            buckets=LATENCY_BUCKETS,
        )
        
        _collectors_initialized = True
        _logger.info(
            "projects_lifecycle_metrics_registered: metrics=[%s, %s]",
            REQUESTS_TOTAL_NAME,
            LATENCY_NAME,
        )
        return True
    except Exception as e:
        _logger.error(
            "projects_lifecycle_metrics_register_error: %s",
            str(e),
            exc_info=True,
        )
        return False


# ---------------------------------------------------------------------------
# Public API - Safe increment/observe functions (no exceptions)
# ---------------------------------------------------------------------------

def inc_lifecycle_request(op: LifecycleOp, outcome: Outcome) -> None:
    """Incrementa contador de operaciones lifecycle."""
    try:
        if _ensure_collectors() and _requests_total:
            _requests_total.labels(op=op, outcome=outcome).inc()
    except Exception:
        pass


def observe_lifecycle_latency(
    latency_seconds: float,
    op: LifecycleOp,
    outcome: Outcome,
) -> None:
    """Registra la latencia de la operación lifecycle."""
    try:
        if _ensure_collectors() and _latency:
            _latency.labels(op=op, outcome=outcome).observe(latency_seconds)
    except Exception:
        pass


def record_lifecycle_metric(
    op: LifecycleOp,
    outcome: Outcome,
    duration_seconds: float,
) -> None:
    """
    Registra una operación lifecycle completa (request + latency).
    
    Args:
        op: Tipo de operación (create, update, close, hard_delete)
        outcome: Resultado (success, error)
        duration_seconds: Duración de la operación en segundos
    """
    inc_lifecycle_request(op, outcome)
    observe_lifecycle_latency(duration_seconds, op, outcome)


# ---------------------------------------------------------------------------
# Context manager para instrumentar operaciones async
# ---------------------------------------------------------------------------
@asynccontextmanager
async def instrument_lifecycle_op(op: LifecycleOp):
    """
    Context manager async para instrumentar operaciones lifecycle.
    
    Uso:
        async with instrument_lifecycle_op("create") as metrics:
            result = await do_create()
            metrics.set_success()
            return result
    
    Si no se llama set_success(), se registra como error.
    """
    class MetricsTracker:
        def __init__(self):
            self._outcome: Outcome = "error"  # Default to error
            self._start = time.perf_counter()
        
        def set_success(self):
            self._outcome = "success"
        
        def set_error(self):
            self._outcome = "error"
        
        @property
        def outcome(self) -> Outcome:
            return self._outcome
        
        @property
        def duration(self) -> float:
            return time.perf_counter() - self._start
    
    tracker = MetricsTracker()
    try:
        yield tracker
    finally:
        record_lifecycle_metric(op, tracker.outcome, tracker.duration)


# ---------------------------------------------------------------------------
# Decorador para instrumentar funciones async
# ---------------------------------------------------------------------------
def instrument_lifecycle(op: LifecycleOp):
    """
    Decorador para instrumentar operaciones lifecycle.
    
    Uso:
        @instrument_lifecycle("create")
        async def create_project(...):
            ...
    
    Registra automáticamente success si no hay excepción, error si la hay.
    """
    import functools
    
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            outcome: Outcome = "error"
            try:
                result = await func(*args, **kwargs)
                outcome = "success"
                return result
            except Exception:
                outcome = "error"
                raise
            finally:
                duration = time.perf_counter() - start
                record_lifecycle_metric(op, outcome, duration)
        return wrapper
    return decorator


__all__ = [
    "inc_lifecycle_request",
    "observe_lifecycle_latency",
    "record_lifecycle_metric",
    "instrument_lifecycle_op",
    "instrument_lifecycle",
    "_ensure_collectors",
    "REQUESTS_TOTAL_NAME",
    "LATENCY_NAME",
    "LifecycleOp",
    "Outcome",
]

# Fin del archivo
