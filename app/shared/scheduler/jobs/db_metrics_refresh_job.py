# -*- coding: utf-8 -*-
"""
backend/app/shared/scheduler/jobs/db_metrics_refresh_job.py

Job programado para refrescar métricas DB → Prometheus.

Se ejecuta cada 60 segundos para mantener los gauges actualizados.
Si falla la conexión a DB, el collector usa valores cacheados.

Autor: DoxAI
Fecha: 2026-01-23
"""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.shared.scheduler import SchedulerService

_logger = logging.getLogger("scheduler.db_metrics")


async def _refresh_db_metrics_task():
    """
    Tarea async que refresca las métricas de DB.
    
    Se ejecuta dentro del contexto del scheduler.
    
    IMPORTANTE: Crea su propia AsyncSession aislada para evitar
    compartir conexiones con otras partes del sistema.
    La sesión se cierra correctamente al finalizar.
    """
    from app.shared.database import async_engine
    from app.shared.observability import get_db_metrics_collector
    from sqlalchemy.ext.asyncio import AsyncSession
    
    db: AsyncSession | None = None
    try:
        collector = get_db_metrics_collector()
        
        # Create isolated session (not shared with request context)
        db = AsyncSession(bind=async_engine, expire_on_commit=False)
        
        result = await collector.refresh(db)
        _logger.debug(
            "db_metrics_refresh_complete ghost=%d jobs_failed=%d",
            result.get("ghost_files_count", -1),
            result.get("jobs_failed_24h", -1),
        )
    except Exception as e:
        _logger.warning(f"db_metrics_refresh_error: {e}")
    finally:
        # Always close the session to release the connection
        if db is not None:
            await db.close()


def register_db_metrics_refresh_job(scheduler: "SchedulerService") -> None:
    """
    Registra el job de refresco de métricas DB.
    
    Args:
        scheduler: Instancia del SchedulerService
    """
    import os
    
    # Allow disabling via env var
    enabled = os.getenv("DB_METRICS_REFRESH_ENABLED", "1").lower() in ("1", "true", "yes")
    
    if not enabled:
        _logger.info("db_metrics_refresh_job disabled via DB_METRICS_REFRESH_ENABLED=0")
        return
    
    # Interval in seconds (default 60)
    interval_seconds = int(os.getenv("DB_METRICS_REFRESH_INTERVAL_SECONDS", "60"))
    
    scheduler.add_interval_job(
        func=_refresh_db_metrics_task,
        job_id="db_metrics_refresh",
        seconds=interval_seconds,
    )
    
    _logger.info(
        "db_metrics_refresh_job registered: interval=%ds",
        interval_seconds,
    )


__all__ = ["register_db_metrics_refresh_job"]
