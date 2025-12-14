
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/metrics/routes/routes_prometheus.py

Rutas para exponer métricas del módulo Projects en formato Prometheus.
La ruta final quedará como:
    GET /projects/metrics/prometheus
cuando este subrouter se incluya bajo el ensamblador principal de Projects.

Ajuste 08/11/2025:
- Endpoint GET /prometheus que devuelve el payload en texto plano (exposition format).
- Uso del exporter interno para mantener paridad con Payments.

Autor: Ixchel Beristain
Fecha de actualización: 08/11/2025
"""
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.modules.projects.metrics.exporters.prometheus_exporter import (
    export_prometheus_text,
)

router = APIRouter(prefix="/metrics", tags=["projects:metrics"])


@router.get(
    "/prometheus",
    response_class=PlainTextResponse,
    summary="Exposición de métricas en formato Prometheus",
    description="Devuelve un texto en el Prometheus exposition format para ser scrapeado.",
)
def prometheus_metrics():
    """
    Genera y devuelve el texto de métricas para Prometheus.
    """
    return PlainTextResponse(content=export_prometheus_text(), media_type="text/plain")

# Fin del archivo backend/app/modules/projects/metrics/routes/routes_prometheus.py
