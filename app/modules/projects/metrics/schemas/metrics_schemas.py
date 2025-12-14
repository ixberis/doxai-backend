
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/metrics/schemas/metrics_schemas.py

Esquemas (Pydantic) para exponer snapshots y estructuras de métricas
del módulo Projects. Se diseñan para mantener paridad conceptual con
el módulo Payments y facilitar la integración con collectors/exporters.

Ajuste 10/11/2025:
- Añade descripciones y ejemplos para Swagger/Redoc.
- Establece límites (ge=0) en contadores/enteros.
- Configura model_config.from_attributes=True (Pydantic v2).
- Mantiene compatibilidad con routes_snapshot_db.py y agregadores DB.

Autor: Ixchel Beristain
Fecha de actualización: 10/11/2025
"""
from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


# ---------------------------------------------------------------------------
# Utilitarios genéricos
# ---------------------------------------------------------------------------
class KeyValueNumber(BaseModel):
    key: str = Field(..., description="Etiqueta o clave")
    value: float = Field(..., description="Valor numérico asociado")

    model_config = ConfigDict(from_attributes=True)


class TimeBucketValue(BaseModel):
    """
    Representa un valor agregado en una ventana temporal (por ejemplo, por día).
    """
    bucket_start: str = Field(..., description="Inicio del bucket (ISO8601, ej. '2025-11-10')")
    value: float = Field(..., description="Valor agregado del bucket")

    model_config = ConfigDict(from_attributes=True)


class HistogramBucket(BaseModel):
    """
    Bucket simple para exposiciones tipo histograma (ej., latencias).
    """
    le: float = Field(..., description="Límite superior (less or equal)")
    count: int = Field(..., ge=0, description="Conteo acumulado del bucket")

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Snapshot: DB
# ---------------------------------------------------------------------------
class ProjectsByState(BaseModel):
    """
    Conteo de proyectos por estado técnico (workflow).
    E.g., draft, processing, ready, error, archived, etc.
    """
    items: Dict[str, int] = Field(default_factory=dict, description="Mapa estado→conteo")
    total: int = Field(0, ge=0, description="Total de proyectos considerados")

    model_config = ConfigDict(from_attributes=True)


class ProjectsByStatus(BaseModel):
    """
    Conteo de proyectos por status administrativo (active, on_hold, etc.).
    """
    items: Dict[str, int] = Field(default_factory=dict, description="Mapa status→conteo")
    total: int = Field(0, ge=0, description="Total de proyectos considerados")

    model_config = ConfigDict(from_attributes=True)


class ProjectFilesSummary(BaseModel):
    """
    Resumen de archivos por proyecto/usuario.
    """
    files_total: int = Field(0, ge=0, description="Total de archivos registrados")
    last_events_total: int = Field(0, ge=0, description="Total de eventos recientes considerados")
    avg_file_size_bytes: Optional[float] = Field(
        None,
        description="Promedio de tamaño en bytes (si aplica en la consulta)",
    )

    model_config = ConfigDict(from_attributes=True)


class ProjectReadyLeadTime(BaseModel):
    """
    Métrica de tiempo desde created -> ready (segundos).
    """
    avg_seconds: Optional[float] = Field(None, description="Promedio created→ready en segundos")
    p50_seconds: Optional[float] = Field(None, description="Percentil 50 (mediana) en segundos")
    p90_seconds: Optional[float] = Field(None, description="Percentil 90 en segundos")
    p99_seconds: Optional[float] = Field(None, description="Percentil 99 en segundos")

    model_config = ConfigDict(from_attributes=True)


class ProjectFileEventsByType(BaseModel):
    """
    Conteo de eventos de archivos por tipo de evento.
    """
    items: Dict[str, int] = Field(default_factory=dict, description="Mapa event_type→conteo")
    total: int = Field(0, ge=0, description="Total de eventos considerados")

    model_config = ConfigDict(from_attributes=True)


class ProjectMetricsSnapshotDB(BaseModel):
    """
    Payload de snapshot desde BD (lecturas/aggregators DB).
    """
    projects_total: int = Field(0, ge=0, description="Total de proyectos")
    projects_by_state: ProjectsByState = Field(
        default_factory=ProjectsByState,
        description="Conteo por estado técnico (workflow)",
    )
    projects_by_status: ProjectsByStatus = Field(
        default_factory=ProjectsByStatus,
        description="Conteo por status administrativo",
    )

    # Ventanas/series temporales (opcional, si las funciones SQL lo devuelven)
    projects_ready_by_window: List[TimeBucketValue] = Field(
        default_factory=list,
        description="Serie de 'ready' por bucket temporal",
    )

    # Tiempos created -> ready (si aplica por vistas/funciones)
    ready_lead_time: ProjectReadyLeadTime = Field(
        default_factory=ProjectReadyLeadTime,
        description="Métricas de lead time created→ready",
    )

    # Archivos y eventos
    files_summary: ProjectFilesSummary = Field(
        default_factory=ProjectFilesSummary,
        description="Resumen de archivos y últimos eventos",
    )
    file_events_by_type: ProjectFileEventsByType = Field(
        default_factory=ProjectFileEventsByType,
        description="Conteo de eventos por tipo",
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "projects_total": 42,
                "projects_by_state": {"items": {"ready": 20, "processing": 15, "error": 7}, "total": 42},
                "projects_by_status": {"items": {"active": 40, "archived": 2}, "total": 42},
                "projects_ready_by_window": [
                    {"bucket_start": "2025-11-08", "value": 5.0},
                    {"bucket_start": "2025-11-09", "value": 7.0},
                    {"bucket_start": "2025-11-10", "value": 8.0}
                ],
                "ready_lead_time": {"avg_seconds": 8123.5, "p50_seconds": 6000.0, "p90_seconds": 12000.0},
                "files_summary": {"files_total": 128, "last_events_total": 512, "avg_file_size_bytes": 7340032.0},
                "file_events_by_type": {"items": {"uploaded": 320, "processed": 150, "failed": 42}, "total": 512}
            }
        },
    )


# ---------------------------------------------------------------------------
# Respuestas estándar de rutas
# ---------------------------------------------------------------------------
class SnapshotDBResponse(BaseModel):
    success: bool = Field(True, description="Indica si la operación fue exitosa")
    snapshot: ProjectMetricsSnapshotDB = Field(..., description="Snapshot consolidado de métricas desde BD")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "success": True,
                "snapshot": ProjectMetricsSnapshotDB.model_construct().model_dump()  # Ejemplo sintético
            }
        },
    )


# ---------------------------------------------------------------------------
# Exposición en __all__ para importación clara
# ---------------------------------------------------------------------------
__all__ = [
    "KeyValueNumber",
    "TimeBucketValue",
    "HistogramBucket",
    "ProjectsByState",
    "ProjectsByStatus",
    "ProjectFilesSummary",
    "ProjectReadyLeadTime",
    "ProjectFileEventsByType",
    "ProjectMetricsSnapshotDB",
    "SnapshotDBResponse",
]

# Fin del archivo backend/app/modules/projects/metrics/schemas/metrics_schemas.py
