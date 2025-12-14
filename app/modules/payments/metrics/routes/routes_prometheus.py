
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/routes/routes_prometheus.py

Rutas Prometheus para el módulo de pagos:
- /payments/metrics            → Export en formato Prometheus
- /payments/metrics/ping       → Health simple del exporter

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

from __future__ import annotations

from typing import Dict, Any

from fastapi import APIRouter
from starlette.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST

from ..exporters.prometheus_exporter import (
    render_prometheus_metrics,
    prometheus_ping,
)

router_prometheus = APIRouter(tags=["payments-metrics"])


@router_prometheus.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics() -> PlainTextResponse:
    """Devuelve las métricas en formato Prometheus para scraping."""
    payload = render_prometheus_metrics()
    return PlainTextResponse(payload, media_type=CONTENT_TYPE_LATEST)


@router_prometheus.get("/metrics/ping")
async def ping() -> Dict[str, Any]:
    """Health-check simple del exporter Prometheus."""
    return prometheus_ping()

# Fin del archivo backend\app\modules\payments\metrics\routes\routes_prometheus.py