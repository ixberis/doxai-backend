
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/metrics/routes/__init__.py

Ensamblador de ruteadores de métricas del módulo Projects.
Incluye:
- /projects/metrics/prometheus
- /projects/metrics/snapshot/db
- /projects/metrics/snapshot/memory
- /projects/metrics/summary  (salud/resumen interno)

Uso:
Este router se debe incluir desde el ensamblador principal del módulo Projects
(`backend/app/modules/projects/routes/__init__.py`) para que los paths queden bajo
el prefijo /projects.

Ajuste 10/11/2025:
- Añade endpoint de healthcheck/resumen (/projects/metrics/summary)
- Manejo seguro si alguna subruta opcional no está disponible.
- Refactor de orden lógico: Prometheus → snapshots → summary.

Autor: Ixchel Beristain
Fecha de actualización: 10/11/2025
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

# Rutas principales
from .routes_prometheus import router as prometheus_router
from .routes_snapshot_db import router as snapshot_db_router

# Manejo seguro para snapshot_memory
try:
    from .routes_snapshot_memory import router as snapshot_memory_router
except ImportError:
    snapshot_memory_router = None

# Collector opcional para healthcheck
try:
    from app.modules.projects.metrics.collectors.metrics_collector import get_collector
except ImportError:
    get_collector = None


def get_projects_metrics_router() -> APIRouter:
    """
    Devuelve un APIRouter con todos los endpoints de métricas del módulo Projects.
    Nota: No usa prefijo aquí; cada subrouter ya define su propio prefix (/metrics/...).
    """
    router = APIRouter(tags=["projects:metrics"])

    # Prometheus exposition format
    router.include_router(prometheus_router)

    # Snapshots
    router.include_router(snapshot_db_router)
    if snapshot_memory_router:
        router.include_router(snapshot_memory_router)

    # Healthcheck / Summary endpoint
    @router.get(
        "/metrics/summary",
        tags=["projects:metrics"],
        summary="Resumen interno de métricas",
        description="Devuelve un resumen rápido de métricas recolectadas (conteo de series, tipos y collector activo).",
        response_model_exclude_none=True,
    )
    def metrics_summary() -> JSONResponse:
        data = {"collector_available": False}
        if get_collector:
            try:
                collector = get_collector()
                snapshot = collector.snapshot()
                data = {
                    "collector_available": True,
                    "metrics_groups": list(snapshot.keys()),
                    "counters": len(snapshot.get("counters", {})),
                    "gauges": len(snapshot.get("gauges", {})),
                    "histograms": len(snapshot.get("histograms", {})),
                }
            except Exception as e:
                data = {"collector_available": False, "error": str(e)}
        return JSONResponse(content=data)

    return router


# Fin del archivo backend/app/modules/projects/metrics/routes/__init__.py
