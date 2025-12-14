
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/metrics/collectors/decorators.py

Decoradores para instrumentar funciones o servicios del módulo Projects.
Permiten registrar métricas de conteo, duración y errores de forma sencilla,
usando el collector en memoria (paridad con Payments).

Ajuste 08/11/2025:
- Decoradores @count_calls y @measure_time_seconds
- Decorador @observe_exceptions para conteo de errores
- Uso seguro (no interrumpe ejecución en caso de error del collector)

Autor: Ixchel Beristain
Fecha de actualización: 08/11/2025
"""
from __future__ import annotations

import functools
import time
from typing import Any, Callable, Optional

from app.modules.projects.metrics.collectors.metrics_collector import get_collector


# ---------------------------------------------------------------------------
# Decorador: contar llamadas exitosas
# ---------------------------------------------------------------------------
def count_calls(metric_name: str):
    """
    Incrementa un contador por cada llamada exitosa de la función decorada.
    Ejemplo:
        @count_calls("projects_processed_total")
        def process_project(...):
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            collector = get_collector()
            try:
                result = func(*args, **kwargs)
                collector.inc_counter(metric_name)
                return result
            except Exception:
                # No incrementamos si falla
                raise
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Decorador: medir duración de ejecución (segundos)
# ---------------------------------------------------------------------------
def measure_time_seconds(metric_name: str, buckets: Optional[list[float]] = None):
    """
    Mide la duración de la función decorada en segundos y la registra
    en un histograma. Ejemplo:
        @measure_time_seconds("projects_ready_time_seconds")
        def finalize_project(...):
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                dt = time.perf_counter() - t0
                try:
                    collector = get_collector()
                    collector.observe(metric_name, dt, buckets=buckets)
                except Exception:
                    # No romper flujo si collector falla
                    pass
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Decorador: contar excepciones
# ---------------------------------------------------------------------------
def observe_exceptions(metric_name: str):
    """
    Incrementa un contador cuando la función lanza una excepción.
    Ejemplo:
        @observe_exceptions("projects_errors_total")
        def process(...):
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception:
                try:
                    collector = get_collector()
                    collector.inc_counter(metric_name)
                except Exception:
                    pass
                raise
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Decorador combinado (ejemplo práctico)
# ---------------------------------------------------------------------------
def instrument(metric_prefix: str):
    """
    Combina conteo y tiempo en un solo decorador.
    Ejemplo:
        @instrument("projects_finalize")
        def finalize(...):
            ...
    Genera:
        - projects_finalize_calls_total
        - projects_finalize_duration_seconds
    """
    def decorator(func: Callable):
        counter_name = f"{metric_prefix}_calls_total"
        duration_name = f"{metric_prefix}_duration_seconds"

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            collector = get_collector()
            t0 = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                collector.inc_counter(counter_name)
                return result
            except Exception:
                # también podríamos tener un contador de errores si se requiere
                raise
            finally:
                dt = time.perf_counter() - t0
                try:
                    collector.observe(duration_name, dt)
                except Exception:
                    pass
        return wrapper
    return decorator


__all__ = [
    "count_calls",
    "measure_time_seconds",
    "observe_exceptions",
    "instrument",
]

# Fin del archivo backend/app/modules/projects/metrics/collectors/decorators.py
