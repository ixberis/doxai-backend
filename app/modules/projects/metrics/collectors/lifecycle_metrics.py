# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/metrics/collectors/lifecycle_metrics.py

Instrumentación de métricas para operaciones lifecycle de proyectos.

Métricas expuestas:
- projects_lifecycle_requests_total{op,outcome}
- projects_lifecycle_latency_seconds{op,outcome}

Labels:
- op: create | update | close | hard_delete
- outcome: success | error

🚫 Prohibido: project_id, auth_user_id (alta cardinalidad)

Autor: Ixchel Beristain
Fecha: 2026-01-28
"""
from __future__ import annotations

import time
from typing import Literal
from contextlib import asynccontextmanager

from app.modules.projects.metrics.collectors.metrics_collector import get_collector


# ---------------------------------------------------------------------------
# Tipos y constantes
# ---------------------------------------------------------------------------
LifecycleOp = Literal["create", "update", "close", "hard_delete"]
Outcome = Literal["success", "error"]

METRIC_REQUESTS = "projects_lifecycle_requests_total"
METRIC_LATENCY = "projects_lifecycle_latency_seconds"


# ---------------------------------------------------------------------------
# Helper para registrar métricas
# ---------------------------------------------------------------------------
def record_lifecycle_metric(
    op: LifecycleOp,
    outcome: Outcome,
    duration_seconds: float,
) -> None:
    """
    Registra una operación lifecycle con su resultado y latencia.
    
    Args:
        op: Tipo de operación (create, update, close, hard_delete)
        outcome: Resultado (success, error)
        duration_seconds: Duración de la operación en segundos
    """
    collector = get_collector()
    
    # Formato con labels: projects_lifecycle_requests_total:op=create:outcome=success
    counter_key = f"{METRIC_REQUESTS}:op={op}:outcome={outcome}"
    latency_key = f"{METRIC_LATENCY}:op={op}:outcome={outcome}"
    
    collector.inc_counter(counter_key)
    collector.observe(latency_key, duration_seconds)


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


# ---------------------------------------------------------------------------
# Snapshot de métricas lifecycle (para diagnóstico)
# ---------------------------------------------------------------------------
def get_lifecycle_metrics_summary() -> dict:
    """
    Devuelve un resumen de las métricas lifecycle actuales.
    
    Útil para diagnóstico y debugging.
    """
    collector = get_collector()
    snapshot = collector.snapshot()
    
    # Filtrar solo métricas lifecycle
    lifecycle_counters = {
        k: v for k, v in snapshot.get("counters", {}).items()
        if k.startswith(METRIC_REQUESTS)
    }
    lifecycle_histograms = {
        k: v for k, v in snapshot.get("histograms", {}).items()
        if k.startswith(METRIC_LATENCY)
    }
    
    return {
        "requests": lifecycle_counters,
        "latency": lifecycle_histograms,
    }


__all__ = [
    "record_lifecycle_metric",
    "instrument_lifecycle_op",
    "instrument_lifecycle",
    "get_lifecycle_metrics_summary",
    "LifecycleOp",
    "Outcome",
]

# Fin del archivo
