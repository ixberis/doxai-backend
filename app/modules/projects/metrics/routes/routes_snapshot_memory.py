
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/metrics/routes/routes_snapshot_memory.py

Rutas para exponer snapshots de métricas del módulo Projects obtenidas
desde memoria (collector in-memory).

Ruta final esperada:
    GET /projects/metrics/snapshot/memory

Ajuste 08/11/2025:
- Endpoint que devuelve el snapshot crudo del collector (counters, gauges, histograms).
- Paridad con Payments snapshot/memory.

Autor: Ixchel Beristain
Fecha de actualización: 08/11/2025
"""
from fastapi import APIRouter

from app.modules.projects.metrics.collectors.metrics_collector import get_collector

router = APIRouter(prefix="/metrics/snapshot", tags=["projects:metrics"])


@router.get(
    "/memory",
    summary="Snapshot de métricas desde memoria",
    description="Devuelve counters, gauges e histogramas tal como están en el collector in-memory.",
)
def snapshot_memory_metrics() -> dict:
    """
    Obtiene el snapshot del collector en memoria.
    Estructura:
    {
        "success": true,
        "snapshot": {
            "counters": {...},
            "gauges": {...},
            "histograms": {...}
        }
    }
    """
    collector = get_collector()
    return {"success": True, "snapshot": collector.snapshot()}

# Fin del archivo backend/app/modules/projects/metrics/routes/routes_snapshot_memory.py
