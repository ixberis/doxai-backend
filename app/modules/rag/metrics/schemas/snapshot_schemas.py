
# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/metrics/schemas/snapshot_schemas.py

Esquemas Pydantic (DTOs) para los snapshots de métricas del módulo RAG.

Incluye dos grandes familias de modelos:
- Snapshots basados en base de datos (RagMetricsDbSnapshot), alimentados por
  las vistas materializadas en el esquema `kpis`.
- Snapshots en memoria (RagMetricsMemorySnapshot), útiles para diagnóstico
  en tiempo real del pipeline de indexación (Fase 1 RAG).

Estos esquemas se usan como `response_model` en los ruteadores:
- /rag/metrics/snapshot/db
- /rag/metrics/snapshot/memory

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


# ============================================================================
# KPIs basados en base de datos
# ============================================================================


class RagDocumentReadinessKpi(BaseModel):
    """Estado de readiness de documentos por proyecto."""
    model_config = ConfigDict(from_attributes=True)

    project_id: str
    documents_total: int
    documents_ready: int
    documents_not_ready: int
    readiness_pct: float


class RagPipelineLatencyKpi(BaseModel):
    """Latencias agregadas del pipeline por día de inicio del job."""
    model_config = ConfigDict(from_attributes=True)

    job_started_date: date
    jobs_count: int
    avg_sec_convert_to_ocr: Optional[float] = None
    avg_sec_ocr_duration: Optional[float] = None
    avg_sec_ocr_to_embed: Optional[float] = None
    p90_sec_convert_to_ocr: Optional[float] = None
    p90_sec_ocr_duration: Optional[float] = None
    p90_sec_ocr_to_embed: Optional[float] = None


class RagOcrCostsDailyKpi(BaseModel):
    """
    Costos diarios de OCR por proveedor/modelo y estrategia de optimización.
    """
    model_config = ConfigDict(from_attributes=True)

    completed_date: date
    provider: str
    provider_model: str
    ocr_optimization: str
    requests_total: int
    pages_total: int
    characters_total: int
    retries_total: int
    cost_total_usd: float


class RagEmbeddingVolumeKpi(BaseModel):
    """Volumen de embeddings por modelo y estado (activo / inactivo)."""
    model_config = ConfigDict(from_attributes=True)

    embedding_model: str
    is_active: bool
    embeddings_total: int


class RagEmbeddingCoverageKpi(BaseModel):
    """
    Cobertura de embeddings por proyecto:
    - Qué proporción de documentos tiene embeddings activos.
    """
    model_config = ConfigDict(from_attributes=True)

    project_id: str
    documents_total: int
    documents_with_embeddings: int
    documents_ready: int
    embedding_coverage_pct: float


class RagMetricsDbSnapshot(BaseModel):
    """
    Snapshot consolidado de KPIs del módulo RAG basado en base de datos.

    Estructura pensada para:
    - Dashboards administrativos.
    - Integración con otros módulos (Projects, Files).
    - Exposición como API estable para monitoreo.
    """

    document_readiness: List[RagDocumentReadinessKpi]
    pipeline_latency: List[RagPipelineLatencyKpi]
    ocr_costs_daily: List[RagOcrCostsDailyKpi]
    embedding_volume: List[RagEmbeddingVolumeKpi]
    embedding_coverage: List[RagEmbeddingCoverageKpi]


# ============================================================================
# Snapshots en memoria
# ============================================================================


class RagRunningJobInfo(BaseModel):
    """Información básica de un job RAG en ejecución."""

    job_id: str
    project_id: Optional[str] = None
    current_phase: Optional[str] = None
    started_at: Optional[datetime] = None


class RagWorkerHealth(BaseModel):
    """
    Estado de salud de un worker/orquestador RAG.

    Útil para monitoreo en vivo:
    - Carga de trabajo.
    - Último heartbeat.
    - Jobs encolados y corriendo.
    """

    worker_name: str
    is_healthy: bool
    last_heartbeat: Optional[datetime] = None
    queued_jobs: int = 0
    running_jobs: int = 0


class RagMetricsMemorySnapshot(BaseModel):
    """
    Snapshot en memoria del módulo RAG.

    Este snapshot NO depende de la base de datos. Refleja:
    - Jobs en ejecución.
    - Estado de los workers.
    - Timestamp del snapshot para referencia temporal.
    """

    running_jobs: List[RagRunningJobInfo]
    workers: List[RagWorkerHealth]
    timestamp: datetime


# Fin del archivo backend/app/modules/rag/metrics/schemas/snapshot_schemas.py
