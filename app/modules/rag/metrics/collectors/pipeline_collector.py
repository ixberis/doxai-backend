# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/metrics/collectors/pipeline_collector.py

Collector de métricas Prometheus para el pipeline del módulo RAG.
Se centra en:
- Estado de readiness de documentos por proyecto.
- Latencias agregadas del pipeline (convert → OCR → embed) por día.

Este collector no accede directamente a la base de datos. En su lugar
recibe DTOs de alto nivel (RagMetricsDbSnapshot) desde el servicio
RagMetricsService y los traduce a métricas Prometheus.

Métricas expuestas (sugeridas):
- rag_document_readiness_pct{project_id}
- rag_documents_total{project_id}
- rag_pipeline_jobs_count{job_started_date}
- rag_pipeline_avg_latency_seconds{stage, job_started_date}
- rag_pipeline_p90_latency_seconds{stage, job_started_date}

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from typing import Optional

from prometheus_client import Gauge

from app.shared.core.metrics_helpers import get_or_create_gauge
from app.modules.rag.metrics.schemas.snapshot_schemas import (
    RagMetricsDbSnapshot,
    RagDocumentReadinessKpi,
    RagPipelineLatencyKpi,
)

# ============================================================================
# Definición de métricas Prometheus
# ============================================================================

# Readiness de documentos por proyecto
DOCUMENT_READINESS_PCT = get_or_create_gauge(
    "rag_document_readiness_pct",
    "Porcentaje de documentos en estado ready por proyecto (RAG Fase 1).",
    labelnames=("project_id",),
)

DOCUMENTS_TOTAL = get_or_create_gauge(
    "rag_documents_total",
    "Número total de documentos indexados por proyecto en el módulo RAG.",
    labelnames=("project_id",),
)

DOCUMENTS_READY = get_or_create_gauge(
    "rag_documents_ready",
    "Número de documentos con estado ready por proyecto en el módulo RAG.",
    labelnames=("project_id",),
)

DOCUMENTS_NOT_READY = get_or_create_gauge(
    "rag_documents_not_ready",
    "Número de documentos aún no ready por proyecto en el módulo RAG.",
    labelnames=("project_id",),
)

# Latencias agregadas del pipeline por día
PIPELINE_JOBS_COUNT = get_or_create_gauge(
    "rag_pipeline_jobs_count",
    "Número de jobs RAG procesados por día de inicio.",
    labelnames=("job_started_date",),
)

PIPELINE_AVG_LATENCY_SECONDS = get_or_create_gauge(
    "rag_pipeline_avg_latency_seconds",
    "Latencia promedio del pipeline RAG por etapa y día (segundos).",
    labelnames=("job_started_date", "stage"),
)

PIPELINE_P90_LATENCY_SECONDS = get_or_create_gauge(
    "rag_pipeline_p90_latency_seconds",
    "Latencia p90 del pipeline RAG por etapa y día (segundos).",
    labelnames=("job_started_date", "stage"),
)


# ============================================================================
# Collector
# ============================================================================


class RagPipelineMetricsCollector:
    """
    Encapsula la lógica para mapear los KPIs de pipeline de RAG (basados en
    base de datos) a métricas Prometheus.

    Uso típico:
        snapshot = RagMetricsService.get_db_snapshot(db)
        RagPipelineMetricsCollector.update_from_snapshot(snapshot)
    """

    @classmethod
    def _update_document_readiness(
        cls, readiness_items: list[RagDocumentReadinessKpi]
    ) -> None:
        """
        Actualiza métricas relacionadas con el estado de readiness de
        documentos por proyecto.
        """
        # Primero, limpiar los labels conocidos para evitar métricas huérfanas.
        DOCUMENT_READINESS_PCT.clear()
        DOCUMENTS_TOTAL.clear()
        DOCUMENTS_READY.clear()
        DOCUMENTS_NOT_READY.clear()

        for item in readiness_items:
            project_id = item.project_id

            DOCUMENT_READINESS_PCT.labels(project_id=project_id).set(
                float(item.readiness_pct)
            )
            DOCUMENTS_TOTAL.labels(project_id=project_id).set(
                float(item.documents_total)
            )
            DOCUMENTS_READY.labels(project_id=project_id).set(
                float(item.documents_ready)
            )
            DOCUMENTS_NOT_READY.labels(project_id=project_id).set(
                float(item.documents_not_ready)
            )

    @classmethod
    def _set_latency_metric(
        cls,
        gauge: Gauge,
        job_started_date: str,
        stage: str,
        value: Optional[float],
    ) -> None:
        """
        Helper para fijar una métrica de latencia si el valor es no nulo.
        """
        if value is None:
            return
        gauge.labels(job_started_date=job_started_date, stage=stage).set(float(value))

    @classmethod
    def _update_pipeline_latency(
        cls, latency_items: list[RagPipelineLatencyKpi]
    ) -> None:
        """
        Actualiza métricas relacionadas con latencias del pipeline RAG por día
        y etapa (convert, ocr, embed).
        """
        PIPELINE_JOBS_COUNT.clear()
        PIPELINE_AVG_LATENCY_SECONDS.clear()
        PIPELINE_P90_LATENCY_SECONDS.clear()

        for item in latency_items:
            # Convertimos la fecha a string ISO para usarla como label
            job_started_date_str = item.job_started_date.isoformat()

            PIPELINE_JOBS_COUNT.labels(
                job_started_date=job_started_date_str
            ).set(float(item.jobs_count))

            # Latencias promedio
            cls._set_latency_metric(
                PIPELINE_AVG_LATENCY_SECONDS,
                job_started_date_str,
                "convert_to_ocr",
                item.avg_sec_convert_to_ocr,
            )
            cls._set_latency_metric(
                PIPELINE_AVG_LATENCY_SECONDS,
                job_started_date_str,
                "ocr_duration",
                item.avg_sec_ocr_duration,
            )
            cls._set_latency_metric(
                PIPELINE_AVG_LATENCY_SECONDS,
                job_started_date_str,
                "ocr_to_embed",
                item.avg_sec_ocr_to_embed,
            )

            # Latencias p90
            cls._set_latency_metric(
                PIPELINE_P90_LATENCY_SECONDS,
                job_started_date_str,
                "convert_to_ocr",
                item.p90_sec_convert_to_ocr,
            )
            cls._set_latency_metric(
                PIPELINE_P90_LATENCY_SECONDS,
                job_started_date_str,
                "ocr_duration",
                item.p90_sec_ocr_duration,
            )
            cls._set_latency_metric(
                PIPELINE_P90_LATENCY_SECONDS,
                job_started_date_str,
                "ocr_to_embed",
                item.p90_sec_ocr_to_embed,
            )

    @classmethod
    def update_from_snapshot(cls, snapshot: RagMetricsDbSnapshot) -> None:
        """
        Punto de entrada principal: recibe un RagMetricsDbSnapshot y actualiza
        todas las métricas de pipeline relevantes.
        """
        cls._update_document_readiness(snapshot.document_readiness)
        cls._update_pipeline_latency(snapshot.pipeline_latency)


# Fin del archivo backend/app/modules/rag/metrics/collectors/pipeline_collector.py
