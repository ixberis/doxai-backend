
# -*- coding: utf-8 -*-
"""
backend/app/observability/http_middleware.py

Middleware ASGI para instrumentación de solicitudes HTTP. Registra contadores
y latencias por método, ruta y estado HTTP, con el fin de generar métricas
Prometheus para el monitoreo de desempeño y carga en la API DoxAI.

Autor: Ixchel Beristain
Fecha: 07/11/2025
"""

from __future__ import annotations
import time
from typing import Callable
from starlette.types import ASGIApp, Receive, Scope, Send
from prometheus_client import Counter, Histogram

_http_requests_total = Counter(
    "doxai_http_requests_total", "Total HTTP requests", ["method", "path", "status"]
)
_http_request_latency = Histogram(
    "doxai_http_request_latency_seconds", "HTTP request latency (s)", ["method", "path", "status"]
)

class PrometheusHTTPMiddleware:
    """
    Middleware ASGI minimalista que instrumenta:
    - Conteo por método/ruta/estatus
    - Histograma de latencia por método/ruta/estatus
    Nota: 'path' idealmente debe ser el path-template (e.g. /users/{id}).
    Si usas FastAPI, puedes inyectar la ruta resuelta desde request.scope['route'].
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        method = scope.get("method", "GET")
        path = scope.get("path", "unknown")
        start = time.perf_counter()
        status_code_container = {"value": "500"}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_code_container["value"] = str(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            status = status_code_container["value"]
            elapsed = time.perf_counter() - start
            # CUIDADO con alta cardinalidad en path: idealmente normalizar a template
            _http_requests_total.labels(method, path, status).inc()
            _http_request_latency.labels(method, path, status).observe(elapsed)

# Fin del archivo backend/app/observability/http_middleware.py
