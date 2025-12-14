
# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/metrics/services/metrics_service.py

Fachada de alto nivel para el servicio de métricas del módulo RAG.

Este archivo concentra una API estable para otros componentes (routers,
orquestador RAG, etc.), delegando el trabajo pesado en servicios
especializados:

- RagDbSnapshotService        → acceso a KPIs en base de datos.
- RagPrometheusMetricsService → actualización de collectors Prometheus.
- RagMemoryMetricsService     → estado en memoria (jobs, workers).

Mantener esta fachada permite:
- Reducir el acoplamiento con detalles internos de implementación.
- Refactorizar los servicios internos sin romper la API externa.
- Usar una única importación desde routers y otros módulos:
    from app.modules.rag.metrics.services.metrics_service import RagMetricsService

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.metrics.schemas.snapshot_schemas import (
    RagMetricsDbSnapshot,
    RagMetricsMemorySnapshot,
    RagRunningJobInfo,
    RagWorkerHealth,
)
from app.modules.rag.metrics.services.db_snapshot_service import RagDbSnapshotService
from app.modules.rag.metrics.services.prometheus_service import (
    RagPrometheusMetricsService,
)
from app.modules.rag.metrics.services.memory_state_service import (
    RagMemoryMetricsService,
)


class RagMetricsService:
    """
    Fachada principal de métricas del módulo RAG.

    Métodos expuestos:
    - get_db_snapshot(db)
    - update_prometheus_metrics(db=None)
    - get_memory_snapshot()
    - register_running_job(...)
    - clear_running_job(job_id)
    - update_worker_health(...)
    """

    # -------------------------------------------------------------------------
    # Snapshots de base de datos
    # -------------------------------------------------------------------------

    @classmethod
    async def get_db_snapshot(cls, db: AsyncSession) -> RagMetricsDbSnapshot:
        """
        Delegación directa a RagDbSnapshotService.get_db_snapshot.
        """
        return await RagDbSnapshotService.get_db_snapshot(db)

    # -------------------------------------------------------------------------
    # Prometheus
    # -------------------------------------------------------------------------

    @classmethod
    async def update_prometheus_metrics(
        cls,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """
        Actualiza los collectors Prometheus del módulo RAG.

        Notas:
        - Si `db` es None, no se refresca desde base de datos (modo no-op).
        - Si se proporciona una sesión, se usan los KPIs más recientes.
        """
        if db is None:
            return

        await RagPrometheusMetricsService.update_from_db(db)

    # -------------------------------------------------------------------------
    # Snapshots en memoria
    # -------------------------------------------------------------------------

    @classmethod
    async def get_memory_snapshot(cls) -> RagMetricsMemorySnapshot:
        """
        Delegación directa a RagMemoryMetricsService.get_snapshot.
        """
        return await RagMemoryMetricsService.get_snapshot()

    @classmethod
    def register_running_job(cls, job_info: RagRunningJobInfo) -> None:
        """
        Delegación a RagMemoryMetricsService.register_running_job.
        """
        RagMemoryMetricsService.register_running_job(job_info)

    @classmethod
    def clear_running_job(cls, job_id: str) -> None:
        """
        Delegación a RagMemoryMetricsService.clear_running_job.
        """
        RagMemoryMetricsService.clear_running_job(job_id)

    @classmethod
    def update_worker_health(cls, health: RagWorkerHealth) -> None:
        """
        Delegación a RagMemoryMetricsService.update_worker_health.
        """
        RagMemoryMetricsService.update_worker_health(health)


# Fin del archivo backend/app/modules/rag/metrics/services/metrics_service.py