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

# Cache for histogram buckets - used to detect conflicting bucket configurations
# Key: (name, labelnames_tuple) to match histogram identity
_HISTOGRAM_BUCKETS_CACHE: Dict[Tuple[str, Tuple[str, ...]], tuple] = globals().get("_HISTOGRAM_BUCKETS_CACHE") or {}


def _get_buckets_cache_key(name: str, labelnames: tuple) -> Tuple[str, Tuple[str, ...]]:
    """Generate cache key for histogram buckets lookup."""
    return (name, tuple(labelnames) if labelnames else ())


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


def get_or_create_histogram(
    name: str,
    description: str,
    labelnames: tuple = (),
    buckets: tuple = None,
) -> Histogram:
    """
    Obtiene histograma existente o crea uno nuevo (evita duplicados en tests/reload).
    
    Args:
        name: Nombre de la métrica
        description: Descripción de la métrica
        labelnames: Tuple de nombres de labels
        buckets: Tuple de bucket boundaries (opcional, usa default de prometheus_client)
    
    Bucket consistency rules:
        - If histogram is created with custom buckets, subsequent calls with DIFFERENT
          buckets raise ValueError (configuration error).
        - If histogram exists and caller omits buckets (None), the existing histogram
          is returned without error (caller defers to original config).
        - Key for bucket cache is (name, labelnames) to avoid false conflicts when
          same metric name is used with different label sets.
    
    Raises:
        ValueError: Si se intenta crear el mismo histograma con buckets diferentes
        RuntimeError: If metric cannot be created or found (should never happen)
    """
    cache_key = _get_cache_key(name, "histogram", labelnames)
    buckets_cache_key = _get_buckets_cache_key(name, labelnames)
    
    # Check for bucket conflicts BEFORE checking cache
    # Only raise if caller explicitly passes different buckets (not None)
    if buckets is not None:
        existing_buckets = _HISTOGRAM_BUCKETS_CACHE.get(buckets_cache_key)
        if existing_buckets is not None and existing_buckets != tuple(buckets):
            raise ValueError(
                f"Histogram '{name}' (labels={labelnames}) already exists with different buckets. "
                f"Existing: {existing_buckets}, Requested: {tuple(buckets)}. "
                f"This is a configuration error - histograms must have consistent bucket definitions."
            )
    
    if cache_key in _METRICS_CACHE:
        return _METRICS_CACHE[cache_key]
    
    existing = _get_existing_metric(name)
    if existing is not None:
        _METRICS_CACHE[cache_key] = existing
        # Store buckets for conflict detection (only if explicitly provided)
        if buckets is not None:
            _HISTOGRAM_BUCKETS_CACHE[buckets_cache_key] = tuple(buckets)
        return existing
    
    try:
        kwargs = {"labelnames": labelnames}
        if buckets is not None:
            kwargs["buckets"] = buckets
        histogram = Histogram(name, description, **kwargs)
        _METRICS_CACHE[cache_key] = histogram
        # Store buckets for conflict detection (only if explicitly provided)
        if buckets is not None:
            _HISTOGRAM_BUCKETS_CACHE[buckets_cache_key] = tuple(buckets)
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
    _HISTOGRAM_BUCKETS_CACHE.clear()


__all__ = [
    "get_or_create_counter",
    "get_or_create_histogram", 
    "get_or_create_gauge",
    "clear_metrics_cache",
]
