
# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/metrics/routes/routes_snapshot_memory.py

Router para exponer snapshots de métricas en memoria para el módulo RAG.
Este endpoint complementa el snapshot de base de datos, permitiendo obtener
estado "en vivo" del pipeline de indexación (Fase 1 RAG), incluyendo:

- Jobs en ejecución.
- Últimas fases procesadas.
- Contadores efímeros actualizados en memoria.
- Métricas no persistidas que ayudan a diagnóstico y monitoreo fino.

Endpoint principal:
- GET /rag/metrics/snapshot/memory

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from fastapi import APIRouter
from app.modules.rag.metrics.schemas.snapshot_schemas import RagMetricsMemorySnapshot
from app.modules.rag.metrics.services.metrics_service import RagMetricsService

router = APIRouter(tags=["RAG Metrics"])


@router.get(
    "/rag/metrics/snapshot/memory",
    response_model=RagMetricsMemorySnapshot,
    summary="Snapshot de métricas en memoria del módulo RAG",
)
async def get_rag_metrics_memory_snapshot() -> RagMetricsMemorySnapshot:
    """
    Regresa un snapshot rápido del estado en memoria del módulo RAG.

    Este endpoint NO consulta la base de datos. En su lugar, refleja:
      - Estado instantáneo del orquestador.
      - Jobs en curso y fases recientes.
      - Contadores o gauges in-memory (si están habilitados).
      - Información de health-check para el servicio OCR y embedders.

    Es útil para:
      - Dashboards internos.
      - Diagnóstico de workers.
      - Verificar que el pipeline está vivo mientras procesa lotes grandes.
    """
    snapshot = await RagMetricsService.get_memory_snapshot()
    return snapshot


# Fin del archivo backend/app/modules/rag/metrics/routes/routes_snapshot_memory.py
