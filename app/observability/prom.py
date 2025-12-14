
# -*- coding: utf-8 -*-
"""
backend/app/observability/prom.py

Configuración de observabilidad Prometheus para DoxAI.

Incluye:
- Middleware HTTP para conteo y latencia por ruta/estado
- Endpoint /metrics compatible con Prometheus (pull model)
- Soporte multiproceso (Prometheus MultiProcess Collector)

Autor: Ixchel Beristain
Fecha: 07/11/2025
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from prometheus_client import (
    CollectorRegistry, multiprocess, generate_latest, CONTENT_TYPE_LATEST,
    Counter, Histogram,
)

# Contadores/Histogramas de capa HTTP (labels saneados: method/path/status)
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_latency_seconds",
    "Latency per request (s)",
    ["method", "path", "status"],
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


def _build_registry() -> Optional[CollectorRegistry]:
    """Inicializa CollectorRegistry con soporte multiproceso (si aplica)."""
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return registry
    return None


def mount_metrics(app: FastAPI, path: str = "/metrics") -> None:
    """Registra el endpoint /metrics en la app FastAPI."""
    registry = _build_registry()

    @app.get(path, include_in_schema=False)
    def metrics():
        data = generate_latest(registry) if registry else generate_latest()
        return Response(content=data, media_type=CONTENT_TYPE_LATEST)


def setup_observability(app: FastAPI) -> None:
    """Agrega middleware de Prometheus y monta el endpoint /metrics."""
    app.add_middleware(PrometheusMiddleware)
    mount_metrics(app)


# Fin del archivo backend/app/observability/prom.py