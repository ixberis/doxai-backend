# -*- coding: utf-8 -*-
"""
backend/app/shared/core/metrics_helpers.py

Helpers para crear métricas Prometheus de forma segura,
evitando duplicados cuando el módulo se recarga (tests).

Autor: Ixchel Beristain
Fecha: 2025-12-22
"""
from prometheus_client import Counter, Histogram, Gauge, REGISTRY


def _get_existing_metric(name: str):
    """Busca una métrica existente en el registry por nombre."""
    names_to_collectors = getattr(REGISTRY, '_names_to_collectors', {})
    return names_to_collectors.get(name)


def get_or_create_counter(name: str, description: str, labelnames: tuple = ()) -> Counter:
    """Obtiene contador existente o crea uno nuevo (evita duplicados en tests)."""
    existing = _get_existing_metric(name)
    if existing is not None:
        return existing
    
    try:
        return Counter(name, description, labelnames=labelnames)
    except ValueError:
        # Ya registrado - recuperar del registry
        return _get_existing_metric(name)


def get_or_create_histogram(name: str, description: str, labelnames: tuple = ()) -> Histogram:
    """Obtiene histograma existente o crea uno nuevo (evita duplicados en tests)."""
    existing = _get_existing_metric(name)
    if existing is not None:
        return existing
    
    try:
        return Histogram(name, description, labelnames=labelnames)
    except ValueError:
        return _get_existing_metric(name)


def get_or_create_gauge(name: str, description: str, labelnames: tuple = ()) -> Gauge:
    """Obtiene gauge existente o crea uno nuevo (evita duplicados en tests)."""
    existing = _get_existing_metric(name)
    if existing is not None:
        return existing
    
    try:
        return Gauge(name, description, labelnames=labelnames)
    except ValueError:
        return _get_existing_metric(name)


__all__ = [
    "get_or_create_counter",
    "get_or_create_histogram", 
    "get_or_create_gauge",
]
