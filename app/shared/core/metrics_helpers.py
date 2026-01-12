# -*- coding: utf-8 -*-
"""
backend/app/shared/core/metrics_helpers.py

Helpers para crear métricas Prometheus de forma segura,
evitando duplicados cuando el módulo se recarga (tests/multiworker).

Design:
- Module-level cache by (name, type, labelnames) - survives importlib.reload()
- Falls back to REGISTRY lookup for edge cases
- Thread-safe via GIL (dict operations are atomic)

Autor: Ixchel Beristain
Fecha: 2025-12-22
Updated: 2026-01-12 - Added module-level cache for reload robustness
"""
from __future__ import annotations

from typing import Dict, Tuple, Any

from prometheus_client import Counter, Histogram, Gauge, REGISTRY


# ─────────────────────────────────────────────────────────────────────────────
# MODULE-LEVEL CACHE
# Survives importlib.reload() by persisting in module globals
# Key: (name, type_name, labelnames_tuple)
# ─────────────────────────────────────────────────────────────────────────────

# CRITICAL: Use globals().get() to survive importlib.reload()
# Without this, the cache dict is recreated on reload, causing duplicate metrics
_METRICS_CACHE: Dict[Tuple[str, str, Tuple[str, ...]]] = globals().get("_METRICS_CACHE") or {}


def _get_cache_key(name: str, type_name: str, labelnames: tuple) -> Tuple[str, str, Tuple[str, ...]]:
    """Generate cache key for metric lookup."""
    return (name, type_name, tuple(labelnames) if labelnames else ())


def _get_existing_metric(name: str):
    """Busca una métrica existente en el registry por nombre."""
    names_to_collectors = getattr(REGISTRY, '_names_to_collectors', {})
    return names_to_collectors.get(name)


def get_or_create_counter(name: str, description: str, labelnames: tuple = ()) -> Counter:
    """
    Obtiene contador existente o crea uno nuevo (evita duplicados en tests/reload).
    
    Uses module-level cache first, then falls back to REGISTRY lookup.
    
    Raises:
        RuntimeError: If metric cannot be created or found (should never happen)
    """
    cache_key = _get_cache_key(name, "counter", labelnames)
    
    # Check module-level cache first (fastest path)
    if cache_key in _METRICS_CACHE:
        return _METRICS_CACHE[cache_key]
    
    # Check REGISTRY (handles multiworker scenarios)
    existing = _get_existing_metric(name)
    if existing is not None:
        _METRICS_CACHE[cache_key] = existing
        return existing
    
    try:
        counter = Counter(name, description, labelnames=labelnames)
        _METRICS_CACHE[cache_key] = counter
        return counter
    except ValueError:
        # Already registered by another thread/worker - recover from registry
        existing = _get_existing_metric(name)
        if existing is not None:
            _METRICS_CACHE[cache_key] = existing
            return existing
        # CRITICAL: Never return None - this is a programming error
        raise RuntimeError(
            f"Failed to create or find counter '{name}': "
            f"ValueError during creation but metric not found in registry"
        )


def get_or_create_histogram(name: str, description: str, labelnames: tuple = ()) -> Histogram:
    """
    Obtiene histograma existente o crea uno nuevo (evita duplicados en tests/reload).
    
    Raises:
        RuntimeError: If metric cannot be created or found (should never happen)
    """
    cache_key = _get_cache_key(name, "histogram", labelnames)
    
    if cache_key in _METRICS_CACHE:
        return _METRICS_CACHE[cache_key]
    
    existing = _get_existing_metric(name)
    if existing is not None:
        _METRICS_CACHE[cache_key] = existing
        return existing
    
    try:
        histogram = Histogram(name, description, labelnames=labelnames)
        _METRICS_CACHE[cache_key] = histogram
        return histogram
    except ValueError:
        existing = _get_existing_metric(name)
        if existing is not None:
            _METRICS_CACHE[cache_key] = existing
            return existing
        raise RuntimeError(
            f"Failed to create or find histogram '{name}': "
            f"ValueError during creation but metric not found in registry"
        )


def get_or_create_gauge(name: str, description: str, labelnames: tuple = ()) -> Gauge:
    """
    Obtiene gauge existente o crea uno nuevo (evita duplicados en tests/reload).
    
    Raises:
        RuntimeError: If metric cannot be created or found (should never happen)
    """
    cache_key = _get_cache_key(name, "gauge", labelnames)
    
    if cache_key in _METRICS_CACHE:
        return _METRICS_CACHE[cache_key]
    
    existing = _get_existing_metric(name)
    if existing is not None:
        _METRICS_CACHE[cache_key] = existing
        return existing
    
    try:
        gauge = Gauge(name, description, labelnames=labelnames)
        _METRICS_CACHE[cache_key] = gauge
        return gauge
    except ValueError:
        existing = _get_existing_metric(name)
        if existing is not None:
            _METRICS_CACHE[cache_key] = existing
            return existing
        raise RuntimeError(
            f"Failed to create or find gauge '{name}': "
            f"ValueError during creation but metric not found in registry"
        )


def clear_metrics_cache() -> None:
    """
    Clear the module-level cache (for testing purposes only).
    
    WARNING: Does NOT unregister metrics from REGISTRY.
    """
    _METRICS_CACHE.clear()


__all__ = [
    "get_or_create_counter",
    "get_or_create_histogram", 
    "get_or_create_gauge",
    "clear_metrics_cache",
]
