
# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/metrics/routes/routes_snapshot_db.py

Router para exponer snapshots de KPIs del módulo RAG directamente desde
la base de datos. Estos snapshots son útiles para:
- Dashboards administrativos ligeros (sin necesidad de Prometheus).
- Herramientas de diagnóstico ad-hoc.
- Integración con otros módulos (p. ej. Projects) que requieren ver el
  estado agregado del pipeline de indexación (Fase 1 RAG).

Endpoint principal:
- GET /rag/metrics/snapshot/db

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.modules.rag.metrics.schemas.snapshot_schemas import RagMetricsDbSnapshot
from app.modules.rag.metrics.services.metrics_service import RagMetricsService

router = APIRouter(tags=["RAG Metrics"])


@router.get(
    "/rag/metrics/snapshot/db",
    response_model=RagMetricsDbSnapshot,
    summary="Snapshot de KPIs RAG desde base de datos",
)
async def get_rag_metrics_db_snapshot(
    db: AsyncSession = Depends(get_db),
) -> RagMetricsDbSnapshot:
    """
    Obtiene un snapshot consistente de los KPIs del módulo RAG desde la base
    de datos, usando las vistas materializadas en el esquema `kpis`.

    El objeto de respuesta incluye, entre otros:
    - Estado de readiness de documentos por proyecto.
    - Latencias agregadas del pipeline por día.
    - Costos diarios de OCR por proveedor/modelo.
    - Volumen de embeddings por modelo y estado (activo/inactivo).
    - Cobertura de embeddings por proyecto.

    Internamente delega en `RagMetricsService.get_db_snapshot`.
    """
    snapshot = await RagMetricsService.get_db_snapshot(db)
    return snapshot


# Fin del archivo backend/app/modules/rag/metrics/routes/routes_snapshot_db.py
