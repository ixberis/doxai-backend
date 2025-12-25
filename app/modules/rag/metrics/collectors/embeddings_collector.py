# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/metrics/collectors/embeddings_collector.py

Collector de métricas Prometheus para la capa de embeddings del módulo RAG.
Se alimenta de los KPIs agregados en base de datos para exponer:

- Volumen de embeddings por modelo y estado (activo/inactivo).
- Cobertura de embeddings por proyecto (qué proporción de documentos
  cuentan con embeddings activos).

Métricas expuestas (sugeridas):
- rag_embeddings_total{embedding_model,is_active}
- rag_embeddings_coverage_pct{project_id}
- rag_documents_with_embeddings{project_id}
- rag_documents_total_with_rag{project_id}

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from app.shared.core.metrics_helpers import get_or_create_gauge

from app.modules.rag.metrics.schemas.snapshot_schemas import (
    RagMetricsDbSnapshot,
    RagEmbeddingVolumeKpi,
    RagEmbeddingCoverageKpi,
)

# ============================================================================
# Definición de métricas Prometheus para embeddings
# ============================================================================

EMBEDDINGS_TOTAL = get_or_create_gauge(
    "rag_embeddings_total",
    "Número total de embeddings por modelo y estado (activo/inactivo).",
    labelnames=("embedding_model", "is_active"),
)

EMBEDDING_COVERAGE_PCT = get_or_create_gauge(
    "rag_embeddings_coverage_pct",
    "Porcentaje de documentos con embeddings activos por proyecto.",
    labelnames=("project_id",),
)

DOCUMENTS_WITH_EMBEDDINGS = get_or_create_gauge(
    "rag_documents_with_embeddings",
    "Número de documentos con embeddings activos por proyecto.",
    labelnames=("project_id",),
)

DOCUMENTS_TOTAL_WITH_RAG = get_or_create_gauge(
    "rag_documents_total_with_rag",
    "Número total de documentos considerados para embeddings por proyecto.",
    labelnames=("project_id",),
)


# ============================================================================
# Collector
# ============================================================================


class RagEmbeddingsMetricsCollector:
    """
    Encapsula la lógica para mapear KPIs de embeddings del módulo RAG
    a métricas Prometheus.

    Uso típico:
        snapshot = RagMetricsService.get_db_snapshot(db)
        RagEmbeddingsMetricsCollector.update_from_snapshot(snapshot)
    """

    @classmethod
    def _update_embedding_volume(
        cls,
        volume_items: list[RagEmbeddingVolumeKpi],
    ) -> None:
        """
        Actualiza métricas relacionadas con el volumen de embeddings por
        modelo y estado (activo / inactivo).
        """
        EMBEDDINGS_TOTAL.clear()

        for item in volume_items:
            EMBEDDINGS_TOTAL.labels(
                embedding_model=item.embedding_model,
                is_active=str(bool(item.is_active)).lower(),
            ).set(float(item.embeddings_total))

    @classmethod
    def _update_embedding_coverage(
        cls,
        coverage_items: list[RagEmbeddingCoverageKpi],
    ) -> None:
        """
        Actualiza métricas relacionadas con la cobertura de embeddings
        por proyecto.
        """
        EMBEDDING_COVERAGE_PCT.clear()
        DOCUMENTS_WITH_EMBEDDINGS.clear()
        DOCUMENTS_TOTAL_WITH_RAG.clear()

        for item in coverage_items:
            project_id = item.project_id

            DOCUMENTS_TOTAL_WITH_RAG.labels(project_id=project_id).set(
                float(item.documents_total)
            )
            DOCUMENTS_WITH_EMBEDDINGS.labels(project_id=project_id).set(
                float(item.documents_with_embeddings)
            )
            EMBEDDING_COVERAGE_PCT.labels(project_id=project_id).set(
                float(item.embedding_coverage_pct)
            )

    @classmethod
    def update_from_snapshot(cls, snapshot: RagMetricsDbSnapshot) -> None:
        """
        Punto de entrada principal: recibe un RagMetricsDbSnapshot y actualiza
        todas las métricas relacionadas con embeddings.
        """
        cls._update_embedding_volume(snapshot.embedding_volume)
        cls._update_embedding_coverage(snapshot.embedding_coverage)


# Fin del archivo backend/app/modules/rag/metrics/collectors/embeddings_collector.py
