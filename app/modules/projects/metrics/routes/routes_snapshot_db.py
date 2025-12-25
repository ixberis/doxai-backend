
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/metrics/routes/routes_snapshot_db.py

Rutas para exponer snapshots de métricas del módulo Projects obtenidas
directamente desde la base de datos (aggregators DB).

Ruta final esperada:
    GET /projects/metrics/snapshot/db

Ajuste 10/11/2025:
- Agrega medición de latencia y contador de requests (Prometheus-friendly).
- Usa labels: endpoint=/projects/metrics/snapshot/db, method=GET, status_code.
- response_model_exclude_none=True para respuestas más ligeras.
- Mantiene compatibilidad con agregadores y schemas existentes.

Ajuste 21/11/2025 (Projects v2):
- Alineado al collector actual (ProjectsMetricsCollector), que expone
  inc_counter(name, amount=1) y observe(name, value_seconds, buckets=None)
  sin etiquetas. Se eliminan las llamadas a métodos inexistentes
  observe_histogram(...) y counters con labels.

Autor: Ixchel Beristain
Fecha de actualización: 21/11/2025
"""
from time import perf_counter
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.shared.database.database import get_db

# Dependencia de DB para este endpoint
# Se usa directamente get_db que puede ser overrideado en tests con sesión sync
get_db_for_metrics = get_db

# Agregadores DB
from app.modules.projects.metrics.aggregators.db.projects import ProjectsDBAggregator
from app.modules.projects.metrics.aggregators.db.files import FilesDBAggregator

# Schemas de respuesta
from app.modules.projects.metrics.schemas.metrics_schemas import (
    ProjectMetricsSnapshotDB,
    SnapshotDBResponse,
)

# Metrics collector (no obligatorio)
from app.modules.projects.metrics.collectors.metrics_collector import get_collector

router = APIRouter(prefix="/metrics/snapshot", tags=["projects:metrics"])


@router.get(
    "/db",
    response_model=SnapshotDBResponse,
    response_model_exclude_none=True,
    summary="Snapshot de métricas desde BD",
    description="Obtiene métricas consolidadas (proyectos, estados, archivos, eventos) directamente desde la base de datos.",
)
def snapshot_db_metrics(db: Session = Depends(get_db_for_metrics)) -> SnapshotDBResponse:
    """
    Lee las métricas desde los agregadores de BD y devuelve un snapshot unificado.
    También registra métricas de latencia y conteo de requests usando el
    collector en memoria si está disponible.
    """
    start = perf_counter()
    collector = None

    # Obtén el collector si existe
    try:
        collector = get_collector()
    except Exception:
        collector = None

    try:
        # Inicializar agregadores
        agg_projects = ProjectsDBAggregator(db)
        agg_files = FilesDBAggregator(db)

        # Construcción de snapshot
        snapshot = ProjectMetricsSnapshotDB(
            projects_total=agg_projects.projects_total(),
            projects_by_state=agg_projects.projects_by_state(),
            projects_by_status=agg_projects.projects_by_status(),
            projects_ready_by_window=agg_projects.projects_ready_by_window(),
            ready_lead_time=agg_projects.ready_lead_time(),
            files_summary=agg_files.files_summary(),
            file_events_by_type=agg_files.events_by_type(),
        )

        return SnapshotDBResponse(success=True, snapshot=snapshot)

    except Exception as e:
        # En caso de error, se registra igualmente la latencia y se lanza 500
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al generar snapshot de métricas: {e}",
        )
    finally:
        duration = perf_counter() - start

        # Registrar métricas en el collector si está disponible
        if collector is not None:
            # Histograma simple de latencias (sin labels)
            try:
                collector.observe("projects_snapshot_db_latency_seconds", duration)
            except Exception:
                pass
            # Contador de requests
            try:
                collector.inc_counter("projects_snapshot_db_requests_total")
            except Exception:
                pass

# Fin del archivo backend/app/modules/projects/metrics/routes/routes_snapshot_db.py
