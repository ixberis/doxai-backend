# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/metrics/services/memory_state_service.py

Servicio especializado en manejar el estado en memoria de métricas del
módulo RAG, principalmente:

- Jobs en ejecución (running_jobs).
- Estado de health de workers/orquestadores RAG.

Responsabilidades:
- Mantener colecciones in-memory de RagRunningJobInfo y RagWorkerHealth.
- Producir un RagMetricsMemorySnapshot para exponer vía API.
- Proveer helpers para registrar/actualizar/eliminar jobs y workers.

NO interactúa con la base de datos ni con Prometheus.

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from __future__ import annotations

from datetime import datetime
from typing import List

from app.modules.rag.metrics.schemas.snapshot_schemas import (
    RagMetricsMemorySnapshot,
    RagRunningJobInfo,
    RagWorkerHealth,
)


class RagMemoryMetricsService:
    """
    Servicio de estado en memoria del módulo RAG.

    Uso típico:
        RagMemoryMetricsService.register_running_job(...)
        RagMemoryMetricsService.update_worker_health(...)
        snapshot = await RagMemoryMetricsService.get_snapshot()
    """

    _running_jobs: List[RagRunningJobInfo] = []
    _workers: List[RagWorkerHealth] = []

    @classmethod
    async def get_snapshot(cls) -> RagMetricsMemorySnapshot:
        """
        Regresa un snapshot inmutable del estado en memoria actual del módulo
        RAG (jobs en ejecución y health de workers).
        """
        running_jobs_copy = list(cls._running_jobs)
        workers_copy = list(cls._workers)

        return RagMetricsMemorySnapshot(
            running_jobs=running_jobs_copy,
            workers=workers_copy,
            timestamp=datetime.utcnow(),
        )

    # -------------------------------------------------------------------------
    # Jobs en ejecución
    # -------------------------------------------------------------------------

    @classmethod
    def register_running_job(cls, job_info: RagRunningJobInfo) -> None:
        """
        Registra o actualiza la información de un job en ejecución.
        """
        cls._running_jobs = [
            j for j in cls._running_jobs if j.job_id != job_info.job_id
        ]
        cls._running_jobs.append(job_info)

    @classmethod
    def clear_running_job(cls, job_id: str) -> None:
        """
        Elimina un job de la lista de jobs en ejecución.
        """
        cls._running_jobs = [j for j in cls._running_jobs if j.job_id != job_id]

    # -------------------------------------------------------------------------
    # Workers / orquestadores
    # -------------------------------------------------------------------------

    @classmethod
    def update_worker_health(cls, health: RagWorkerHealth) -> None:
        """
        Registra o actualiza el estado de salud de un worker del módulo RAG.
        """
        cls._workers = [
            w for w in cls._workers if w.worker_name != health.worker_name
        ]
        cls._workers.append(health)


# Fin del archivo backend/app/modules/rag/metrics/services/memory_state_service.py

