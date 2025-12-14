
# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/metrics/routes/routes_prometheus.py

Router de métricas Prometheus para el módulo RAG.
Exponer métricas vía un endpoint HTTP es obligatorio para que el stack de
monitorización (Prometheus + Grafana) recolecte, procese y grafique el 
estado del pipeline RAG Fase 1 (indexación).

Este archivo:
- Define el endpoint: GET /rag/metrics/prometheus
- Actualiza los collectors leyendo KPIs desde la base de datos
- Retorna las métricas en el formato oficial de Prometheus (text/plain)

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from fastapi import APIRouter, Depends, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.modules.rag.metrics.services.metrics_service import RagMetricsService

router = APIRouter(tags=["RAG Metrics"])


@router.get("/rag/metrics/prometheus")
async def prometheus_metrics(
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Endpoint para exponer métricas Prometheus del módulo RAG.

    Flujo:
    1. Llamamos al servicio que actualiza los gauges, counters e histogramas
       leyendo los KPIs de la base de datos (esquema kpis).
    2. generate_latest() produce el texto en formato Prometheus.
    3. Se devuelve con media_type adecuado.
    """
    await RagMetricsService.update_prometheus_metrics(db=db)
    metrics_data = generate_latest()
    return Response(metrics_data, media_type=CONTENT_TYPE_LATEST)


# Fin del archivo backend/app/modules/rag/metrics/routes/routes_prometheus.py

