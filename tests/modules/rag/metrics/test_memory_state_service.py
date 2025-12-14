
# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/metrics/test_memory_state_service.py

Pruebas unitarias para RagMemoryMetricsService, responsable de mantener
estado en memoria sobre jobs en ejecución y health de workers en el
módulo RAG.

Se valida:
- Registro y eliminación de jobs en ejecución.
- Registro y actualización de estado de workers.
- Generación de snapshot coherente.

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

import pytest

from app.modules.rag.metrics.schemas.snapshot_schemas import (
    RagRunningJobInfo,
    RagWorkerHealth,
)
from app.modules.rag.metrics.services.memory_state_service import (
    RagMemoryMetricsService,
)


@pytest.mark.anyio
async def test_memory_snapshot_register_job_and_worker():
    """Debe ser posible registrar un job y un worker y verlos en el snapshot."""
    # Limpiamos estado global inicial
    RagMemoryMetricsService._running_jobs = []
    RagMemoryMetricsService._workers = []

    job = RagRunningJobInfo(job_id="job-123", project_id="proj-1", current_phase="convert")
    worker = RagWorkerHealth(
        worker_name="worker-1",
        is_healthy=True,
        queued_jobs=2,
        running_jobs=1,
    )

    RagMemoryMetricsService.register_running_job(job)
    RagMemoryMetricsService.update_worker_health(worker)

    snapshot = await RagMemoryMetricsService.get_snapshot()

    assert len(snapshot.running_jobs) == 1
    assert snapshot.running_jobs[0].job_id == "job-123"

    assert len(snapshot.workers) == 1
    assert snapshot.workers[0].worker_name == "worker-1"
    assert snapshot.workers[0].is_healthy is True
    assert snapshot.timestamp is not None


@pytest.mark.anyio
async def test_clear_running_job():
    """clear_running_job debe eliminar el job del snapshot."""
    RagMemoryMetricsService._running_jobs = []
    job = RagRunningJobInfo(job_id="job-xyz", project_id="proj-x", current_phase="ocr")
    RagMemoryMetricsService.register_running_job(job)

    snapshot_before = await RagMemoryMetricsService.get_snapshot()
    assert any(j.job_id == "job-xyz" for j in snapshot_before.running_jobs)

    RagMemoryMetricsService.clear_running_job("job-xyz")
    snapshot_after = await RagMemoryMetricsService.get_snapshot()
    assert all(j.job_id != "job-xyz" for j in snapshot_after.running_jobs)


# Fin del archivo backend/tests/modules/rag/metrics/test_memory_state_service.py
