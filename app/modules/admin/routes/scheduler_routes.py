# -*- coding: utf-8 -*-
"""
backend/app/modules/admin/routes/scheduler_routes.py

Endpoints de administración para monitoreo del scheduler.

Proporciona información sobre:
- Jobs activos y próximas ejecuciones
- Estado individual de jobs
- Estadísticas históricas de limpieza de caché
- Control de jobs (pausar, reanudar, ejecutar manualmente)

PROTECTED: Requires admin role via require_admin_strict dependency.

Autor: DoxAI
Fecha: 2025-11-05
Updated: 2026-01-13 (Use require_admin_strict for JWT-based auth)
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, Protocol, runtime_checkable
from datetime import datetime, timedelta

from app.shared.scheduler import get_scheduler, SchedulerService
from app.modules.files.services.cache import get_metadata_cache
from app.modules.admin.services.cache_stats_normalizer import normalize_cache_stats
from app.modules.auth.dependencies import require_admin_strict


@runtime_checkable
class SchedulerServiceProtocol(Protocol):
    """Protocol para abstracción del scheduler en tests."""
    
    @property
    def is_running(self) -> bool: ...
    
    def get_jobs(self) -> list: ...
    
    def get_job_status(self, job_id: str) -> Optional[dict]: ...


def get_scheduler_service() -> SchedulerServiceProtocol:
    """Dependency inyectable para obtener el scheduler."""
    return get_scheduler()


router = APIRouter(
    prefix="/admin/scheduler",
    tags=["admin-scheduler"],
    dependencies=[Depends(require_admin_strict)],  # All routes require admin
)


# ==================== JOBS ENDPOINTS ====================

@router.get("/jobs")
async def list_scheduled_jobs(
    scheduler: SchedulerServiceProtocol = Depends(get_scheduler_service)
):
    """
    Lista todos los jobs programados activos.
    
    Requires: Bearer token with admin role.
    
    Returns:
        Dict con estado del scheduler y lista de jobs:
        - is_running: Bool indicando si el scheduler está activo
        - jobs: Lista de jobs con información de cada uno
    
    Response Example:
        {
          "is_running": true,
          "jobs": [
            {
              "id": "cache_cleanup_hourly",
              "name": "cache_cleanup_hourly",
              "next_run": "2025-11-05T15:00:00",
              "trigger": "interval[1:00:00]"
            }
          ]
        }
    """
    return {
        "is_running": scheduler.is_running,
        "jobs": scheduler.get_jobs()
    }


@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    scheduler: SchedulerServiceProtocol = Depends(get_scheduler_service)
):
    """
    Obtiene información detallada de un job específico.
    
    Requires: Bearer token with admin role.
    
    Args:
        job_id: ID del job
    
    Returns:
        Dict con información del job:
        - id: ID del job
        - name: Nombre del job
        - next_run: Próxima ejecución
        - trigger: Configuración del trigger
        - pending: Si tiene ejecución pendiente
    
    Raises:
        HTTPException 404: Si el job no existe
    
    Response Example:
        {
          "id": "cache_cleanup_hourly",
          "name": "cache_cleanup_hourly",
          "next_run": "2025-11-05T15:00:00",
          "trigger": "interval[1:00:00]",
          "pending": false
        }
    """
    status = scheduler.get_job_status(job_id)
    
    if not status:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' no encontrado"
        )
    
    return status


@router.post("/jobs/{job_id}/pause")
async def pause_job(
    job_id: str,
    scheduler: SchedulerServiceProtocol = Depends(get_scheduler_service)
):
    """
    Pausa un job programado.
    
    Requires: Bearer token with admin role.
    
    Args:
        job_id: ID del job a pausar
    
    Returns:
        Dict confirmando la operación
    
    Raises:
        HTTPException 404: Si el job no existe
    """
    try:
        scheduler._scheduler.pause_job(job_id)
        return {
            "message": f"Job '{job_id}' pausado",
            "job_id": job_id,
            "status": "paused"
        }
    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"Error pausando job '{job_id}': {str(e)}"
        )


@router.post("/jobs/{job_id}/resume")
async def resume_job(
    job_id: str,
    scheduler: SchedulerServiceProtocol = Depends(get_scheduler_service)
):
    """
    Reanuda un job pausado.
    
    Requires: Bearer token with admin role.
    
    Args:
        job_id: ID del job a reanudar
    
    Returns:
        Dict confirmando la operación
    
    Raises:
        HTTPException 404: Si el job no existe
    """
    try:
        scheduler._scheduler.resume_job(job_id)
        return {
            "message": f"Job '{job_id}' reanudado",
            "job_id": job_id,
            "status": "active"
        }
    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"Error reanudando job '{job_id}': {str(e)}"
        )


@router.post("/jobs/{job_id}/run-now")
async def run_job_now(
    job_id: str,
    scheduler: SchedulerServiceProtocol = Depends(get_scheduler_service)
):
    """
    Ejecuta un job manualmente de inmediato.
    
    Requires: Bearer token with admin role.
    
    Args:
        job_id: ID del job a ejecutar
    
    Returns:
        Dict con resultado de la ejecución
    
    Raises:
        HTTPException 404: Si el job no existe
    """
    try:
        # Obtener el job
        job = scheduler._scheduler.get_job(job_id)
        if not job:
            raise HTTPException(
                status_code=404,
                detail=f"Job '{job_id}' no encontrado"
            )
        
        # Ejecutar el job manualmente
        result = await job.func(**job.kwargs)
        
        return {
            "message": f"Job '{job_id}' ejecutado manualmente",
            "job_id": job_id,
            "timestamp": datetime.utcnow().isoformat(),
            "result": result
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error ejecutando job '{job_id}': {str(e)}"
        )


# ==================== ESTADÍSTICAS ENDPOINTS ====================

@router.get("/stats/cache-cleanup")
async def get_cache_cleanup_stats(
    days: int = 7,
):
    """
    Obtiene estadísticas históricas de limpieza de caché.
    
    Requires: Bearer token with admin role.
    
    Args:
        days: Número de días de historial (default: 7)
    
    Returns:
        Dict con estadísticas agregadas y desglosadas:
        - period: Período de análisis
        - summary: Resumen agregado
        - history: Lista de ejecuciones individuales
    
    Response Example:
        {
          "period": {
            "start": "2025-10-29T00:00:00",
            "end": "2025-11-05T14:00:00",
            "days": 7
          },
          "summary": {
            "total_executions": 168,
            "total_entries_removed": 12500,
            "total_memory_freed_kb": 25000,
            "average_duration_ms": 45.3,
            "average_hit_rate": 78.5
          },
          "history": [
            {
              "timestamp": "2025-11-05T14:00:00",
              "entries_removed": 150,
              "memory_freed_kb": 300,
              "duration_ms": 45.67,
              "hit_rate": 78.5
            }
          ]
        }
    
    Note:
        En esta implementación, las estadísticas se simulan ya que no tenemos
        persistencia real. En producción, deberías almacenar las estadísticas
        en una tabla de base de datos.
    """
    # Obtener estadísticas actuales del caché y normalizarlas
    cache = get_metadata_cache()
    raw_stats = cache.get_stats()
    current_stats = normalize_cache_stats(raw_stats)
    
    # En producción, estas estadísticas vendrían de la BD
    # Por ahora, simulamos datos históricos basados en el estado actual
    now = datetime.utcnow()
    start_date = now - timedelta(days=days)
    
    # Simular historial (en producción, esto vendría de la BD)
    history = []
    for i in range(days * 24):  # Una ejecución por hora
        timestamp = start_date + timedelta(hours=i)
        if timestamp <= now:
            history.append({
                "timestamp": timestamp.isoformat(),
                "entries_removed": 50 + (i % 200),
                "memory_freed_kb": 100 + (i % 400),
                "duration_ms": 30.0 + (i % 50),
                "hit_rate": 70.0 + (i % 20)
            })
    
    # Calcular resumen
    total_executions = len(history)
    total_entries_removed = sum(h["entries_removed"] for h in history)
    total_memory_freed_kb = sum(h["memory_freed_kb"] for h in history)
    avg_duration_ms = sum(h["duration_ms"] for h in history) / total_executions if total_executions > 0 else 0
    avg_hit_rate = sum(h["hit_rate"] for h in history) / total_executions if total_executions > 0 else 0
    
    return {
        "period": {
            "start": start_date.isoformat(),
            "end": now.isoformat(),
            "days": days
        },
        "summary": {
            "total_executions": total_executions,
            "total_entries_removed": total_entries_removed,
            "total_memory_freed_kb": total_memory_freed_kb,
            "average_duration_ms": round(avg_duration_ms, 2),
            "average_hit_rate": round(avg_hit_rate, 2),
            "current_cache_size": current_stats["size"],
            "current_hit_rate": current_stats["hit_rate"]
        },
        "history": history[-24:],  # Últimas 24 horas para no saturar
        "note": "Historial simulado. En producción, implementar persistencia en BD."
    }


@router.get("/health")
async def scheduler_health(
    scheduler: SchedulerServiceProtocol = Depends(get_scheduler_service)
):
    """
    Verifica el estado de salud del scheduler.
    
    Requires: Bearer token with admin role.
    
    Returns:
        Dict con estado de salud:
        - status: healthy | degraded | unhealthy
        - is_running: Si el scheduler está activo
        - jobs_count: Número de jobs registrados
        - warnings: Lista de advertencias si existen
    
    Response Example:
        {
          "status": "healthy",
          "is_running": true,
          "jobs_count": 1,
          "warnings": []
        }
    """
    jobs = scheduler.get_jobs()
    
    warnings = []
    status = "healthy"
    
    # Verificar si el scheduler está corriendo
    if not scheduler.is_running:
        status = "unhealthy"
        warnings.append("Scheduler no está activo")
    
    # Verificar si hay jobs registrados
    if len(jobs) == 0:
        status = "degraded"
        warnings.append("No hay jobs registrados")
    
    # Verificar próximas ejecuciones
    for job in jobs:
        if job["next_run"] is None:
            warnings.append(f"Job '{job['id']}' sin próxima ejecución programada")
            if status == "healthy":
                status = "degraded"
    
    return {
        "status": status,
        "is_running": scheduler.is_running,
        "jobs_count": len(jobs),
        "warnings": warnings
    }


# Fin del archivo backend/app/modules/admin/routes/scheduler_routes.py
