
# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/metrics/services/prometheus_service.py

Servicio especializado en actualizar los collectors Prometheus del módulo RAG
a partir de un snapshot de base de datos.

Responsabilidades:
- Consumir RagMetricsDbSnapshot (típicamente producido por
  RagDbSnapshotService).
- Invocar los collectors especializados:
    * RagPipelineMetricsCollector
    * RagOcrMetricsCollector
    * RagEmbeddingsMetricsCollector

NO accede directamente a la base de datos ni mantiene estado en memoria.

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.metrics.collectors.pipeline_collector import (
    RagPipelineMetricsCollector,
)
from app.modules.rag.metrics.collectors.ocr_collector import RagOcrMetricsCollector
from app.modules.rag.metrics.collectors.embeddings_collector import (
    RagEmbeddingsMetricsCollector,
)
from app.modules.rag.metrics.schemas.snapshot_schemas import RagMetricsDbSnapshot
from app.modules.rag.metrics.services.db_snapshot_service import RagDbSnapshotService


class RagPrometheusMetricsService:
    """
    Servicio que concentra la actualización de métricas Prometheus
    basadas en los KPIs de base de datos del módulo RAG.
    """

    @classmethod
    async def update_from_db(cls, db: AsyncSession) -> None:
        """
        Obtiene un snapshot completo desde base de datos y actualiza todos
        los collectors Prometheus del módulo RAG.
        """
        snapshot = await RagDbSnapshotService.get_db_snapshot(db)
        cls.update_from_snapshot(snapshot)

    @classmethod
    def update_from_snapshot(cls, snapshot: RagMetricsDbSnapshot) -> None:
        """
        Actualiza los collectors Prometheus usando un RagMetricsDbSnapshot
        ya construido.
        """
        RagPipelineMetricsCollector.update_from_snapshot(snapshot)
        RagOcrMetricsCollector.update_from_snapshot(snapshot)
        RagEmbeddingsMetricsCollector.update_from_snapshot(snapshot)


# Fin del archivo backend/app/modules/rag/metrics/services/prometheus_service.py
