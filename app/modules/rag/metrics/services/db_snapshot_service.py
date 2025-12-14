
# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/metrics/services/db_snapshot_service.py

Servicio especializado en construir snapshots de KPIs del módulo RAG
directamente desde la base de datos (esquema `kpis`).

Responsabilidades:
- Ejecutar consultas sobre las vistas materializadas:
    * kpis.mv_rag_document_readiness
    * kpis.mv_rag_pipeline_latency
    * kpis.mv_rag_ocr_costs_daily
    * kpis.mv_rag_embedding_volume
    * kpis.mv_rag_embedding_coverage
- Mapear los resultados a DTOs Pydantic.
- Consolidar todo en un RagMetricsDbSnapshot.

Este servicio NO conoce nada de Prometheus ni de estado en memoria.

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from __future__ import annotations

from typing import List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.metrics.schemas.snapshot_schemas import (
    RagMetricsDbSnapshot,
    RagDocumentReadinessKpi,
    RagPipelineLatencyKpi,
    RagOcrCostsDailyKpi,
    RagEmbeddingVolumeKpi,
    RagEmbeddingCoverageKpi,
)


class RagDbSnapshotService:
    """
    Servicio de acceso a KPIs de RAG en base de datos.

    Punto de entrada público:
        snapshot = await RagDbSnapshotService.get_db_snapshot(db)
    """

    @classmethod
    async def get_db_snapshot(cls, db: AsyncSession) -> RagMetricsDbSnapshot:
        """
        Construye un RagMetricsDbSnapshot a partir de las vistas materializadas
        en el esquema `kpis`.
        """
        document_readiness = await cls._load_document_readiness(db)
        pipeline_latency = await cls._load_pipeline_latency(db)
        ocr_costs_daily = await cls._load_ocr_costs_daily(db)
        embedding_volume = await cls._load_embedding_volume(db)
        embedding_coverage = await cls._load_embedding_coverage(db)

        return RagMetricsDbSnapshot(
            document_readiness=document_readiness,
            pipeline_latency=pipeline_latency,
            ocr_costs_daily=ocr_costs_daily,
            embedding_volume=embedding_volume,
            embedding_coverage=embedding_coverage,
        )

    # -------------------------------------------------------------------------
    # Lecturas específicas de cada vista materializada
    # -------------------------------------------------------------------------

    @classmethod
    async def _load_document_readiness(
        cls,
        db: AsyncSession,
    ) -> List[RagDocumentReadinessKpi]:
        result = await db.execute(
            text(
                """
                SELECT
                  project_id,
                  documents_total,
                  documents_ready,
                  documents_not_ready,
                  readiness_pct
                FROM kpis.mv_rag_document_readiness
                """
            )
        )
        items: List[RagDocumentReadinessKpi] = []
        for row in result.mappings():
            items.append(
                RagDocumentReadinessKpi(
                    project_id=row["project_id"],
                    documents_total=row["documents_total"],
                    documents_ready=row["documents_ready"],
                    documents_not_ready=row["documents_not_ready"],
                    readiness_pct=float(row["readiness_pct"]),
                )
            )
        return items

    @classmethod
    async def _load_pipeline_latency(
        cls,
        db: AsyncSession,
    ) -> List[RagPipelineLatencyKpi]:
        result = await db.execute(
            text(
                """
                SELECT
                  job_started_date,
                  jobs_count,
                  avg_sec_convert_to_ocr,
                  avg_sec_ocr_duration,
                  avg_sec_ocr_to_embed,
                  p90_sec_convert_to_ocr,
                  p90_sec_ocr_duration,
                  p90_sec_ocr_to_embed
                FROM kpis.mv_rag_pipeline_latency
                ORDER BY job_started_date DESC
                """
            )
        )
        items: List[RagPipelineLatencyKpi] = []
        for row in result.mappings():
            items.append(
                RagPipelineLatencyKpi(
                    job_started_date=row["job_started_date"],
                    jobs_count=row["jobs_count"],
                    avg_sec_convert_to_ocr=row["avg_sec_convert_to_ocr"],
                    avg_sec_ocr_duration=row["avg_sec_ocr_duration"],
                    avg_sec_ocr_to_embed=row["avg_sec_ocr_to_embed"],
                    p90_sec_convert_to_ocr=row["p90_sec_convert_to_ocr"],
                    p90_sec_ocr_duration=row["p90_sec_ocr_duration"],
                    p90_sec_ocr_to_embed=row["p90_sec_ocr_to_embed"],
                )
            )
        return items

    @classmethod
    async def _load_ocr_costs_daily(
        cls,
        db: AsyncSession,
    ) -> List[RagOcrCostsDailyKpi]:
        result = await db.execute(
            text(
                """
                SELECT
                  completed_date,
                  provider,
                  provider_model,
                  ocr_optimization,
                  requests_total,
                  pages_total,
                  characters_total,
                  retries_total,
                  cost_total_usd
                FROM kpis.mv_rag_ocr_costs_daily
                ORDER BY completed_date DESC
                """
            )
        )
        items: List[RagOcrCostsDailyKpi] = []
        for row in result.mappings():
            items.append(
                RagOcrCostsDailyKpi(
                    completed_date=row["completed_date"],
                    provider=row["provider"],
                    provider_model=row["provider_model"],
                    ocr_optimization=row["ocr_optimization"],
                    requests_total=row["requests_total"],
                    pages_total=row["pages_total"],
                    characters_total=row["characters_total"],
                    retries_total=row["retries_total"],
                    cost_total_usd=float(row["cost_total_usd"]),
                )
            )
        return items

    @classmethod
    async def _load_embedding_volume(
        cls,
        db: AsyncSession,
    ) -> List[RagEmbeddingVolumeKpi]:
        result = await db.execute(
            text(
                """
                SELECT
                  embedding_model,
                  is_active,
                  embeddings_total
                FROM kpis.mv_rag_embedding_volume
                """
            )
        )
        items: List[RagEmbeddingVolumeKpi] = []
        for row in result.mappings():
            items.append(
                RagEmbeddingVolumeKpi(
                    embedding_model=row["embedding_model"],
                    is_active=row["is_active"],
                    embeddings_total=row["embeddings_total"],
                )
            )
        return items

    @classmethod
    async def _load_embedding_coverage(
        cls,
        db: AsyncSession,
    ) -> List[RagEmbeddingCoverageKpi]:
        result = await db.execute(
            text(
                """
                SELECT
                  project_id,
                  documents_total,
                  documents_with_embeddings,
                  documents_ready,
                  embedding_coverage_pct
                FROM kpis.mv_rag_embedding_coverage
                """
            )
        )
        items: List[RagEmbeddingCoverageKpi] = []
        for row in result.mappings():
            items.append(
                RagEmbeddingCoverageKpi(
                    project_id=row["project_id"],
                    documents_total=row["documents_total"],
                    documents_with_embeddings=row["documents_with_embeddings"],
                    documents_ready=row["documents_ready"],
                    embedding_coverage_pct=float(row["embedding_coverage_pct"]),
                )
            )
        return items


# Fin del archivo backend/app/modules/rag/metrics/services/db_snapshot_service.py
