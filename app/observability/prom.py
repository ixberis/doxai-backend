# -*- coding: utf-8 -*-
"""
backend/app/observability/prom.py

Configuración de observabilidad Prometheus para DoxAI.

Incluye:
- Middleware HTTP para conteo y latencia por ruta/estado
- Endpoint /metrics compatible con Prometheus (pull model)
- Soporte multiproceso (Prometheus MultiProcess Collector)

IMPORTANTE (2026-01-24):
- /metrics SIEMPRE usa prometheus_client.REGISTRY (el registry global)
- Esto asegura que las métricas registradas via get_or_create_* aparezcan
- MultiProcessCollector se añade solo para agregar métricas de workers
- process_* y python_info también aparecen porque están en REGISTRY

Autor: Ixchel Beristain
Fecha: 07/11/2025
Updated: 2026-01-24 - Fixed registry issue where custom metrics didn't appear
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from prometheus_client import (
    CollectorRegistry, multiprocess, generate_latest, CONTENT_TYPE_LATEST, REGISTRY,
)

from app.shared.core.metrics_helpers import (
    get_or_create_counter,
    get_or_create_histogram,
)

_logger = logging.getLogger("observability.prom")


# Contadores/Histogramas de capa HTTP (labels saneados: method/path/status)
REQUEST_COUNT = get_or_create_counter(
    "http_requests_total",
    "Total HTTP requests",
    labelnames=("method", "path", "status"),
)
REQUEST_LATENCY = get_or_create_histogram(
    "http_request_latency_seconds",
    "Latency per request (s)",
    labelnames=("method", "path", "status"),
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware para instrumentar peticiones HTTP en FastAPI."""

    async def dispatch(self, request, call_next):
        method = request.method
        path = request.url.path

        # Medimos latencia y registramos status una sola vez
        from time import perf_counter
        start = perf_counter()
        resp = await call_next(request)
        elapsed = perf_counter() - start

        status = str(resp.status_code)
        REQUEST_LATENCY.labels(method, path, status).observe(elapsed)
        REQUEST_COUNT.labels(method, path, status).inc()
        return resp


def _get_metrics_registry() -> CollectorRegistry:
    """
    Obtiene el registry correcto para /metrics.
    
    CRITICAL FIX (2026-01-24):
    - SIEMPRE retorna REGISTRY (el global) que contiene:
      - Platform collectors (process_*, python_info)
      - Métricas HTTP (http_requests_total, http_request_latency_seconds)
      - Métricas custom (files_delete_*, touch_debounced_*, doxai_*)
    
    - Si PROMETHEUS_MULTIPROC_DIR está configurado:
      - Añade MultiProcessCollector al REGISTRY para agregar métricas de workers
      - Pero NO crea un registry nuevo vacío
    
    Returns:
        El registry global de prometheus_client (REGISTRY)
    """
    multiproc_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    
    if multiproc_dir:
        # Multiprocess mode: agregar collector para combinar métricas de workers
        # pero usar el REGISTRY global que ya tiene nuestras métricas
        try:
            # Only add MultiProcessCollector once
            if not hasattr(REGISTRY, "_multiprocess_collector_added"):
                multiprocess.MultiProcessCollector(REGISTRY)
                REGISTRY._multiprocess_collector_added = True
                _logger.info(
                    "prometheus_multiprocess_enabled: dir=%s registry=REGISTRY",
                    multiproc_dir,
                )
        except Exception as e:
            # MultiProcessCollector may already be registered or other error
            _logger.warning("prometheus_multiprocess_setup_error: %s", e)
    
    return REGISTRY


def mount_metrics(app: FastAPI, path: str = "/metrics") -> None:
    """
    Registra el endpoint /metrics en la app FastAPI.
    
    Usa el registry global (REGISTRY) que contiene todas las métricas.
    """
    registry = _get_metrics_registry()
    
    # Diagnostic: log registry info at mount time
    try:
        families = list(registry.collect())
        names_to_collectors = getattr(registry, "_names_to_collectors", {})
        
        has_files_delete = "files_delete_total" in names_to_collectors
        has_touch = "touch_debounced_allowed_total" in names_to_collectors
        has_doxai = "doxai_ghost_files_count" in names_to_collectors
        
        _logger.info(
            "prometheus_metrics_mounted: path=%s families=%d has_files_delete=%s has_touch=%s has_doxai=%s",
            path,
            len(families),
            has_files_delete,
            has_touch,
            has_doxai,
        )
    except Exception as e:
        _logger.warning("prometheus_metrics_mount_error: %s", e)

    @app.get(path, include_in_schema=False)
    def metrics():
        """Endpoint /metrics para Prometheus scraping."""
        data = generate_latest(registry)
        return Response(content=data, media_type=CONTENT_TYPE_LATEST)


def setup_observability(app: FastAPI) -> None:
    """Agrega middleware de Prometheus y monta el endpoint /metrics."""
    app.add_middleware(PrometheusMiddleware)
    mount_metrics(app)
    _logger.info("prometheus_observability_setup_complete")


# Fin del archivo backend/app/observability/prom.py