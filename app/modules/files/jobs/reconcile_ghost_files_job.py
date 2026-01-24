# -*- coding: utf-8 -*-
"""
backend/app/modules/files/jobs/reconcile_ghost_files_job.py

Job automático para reconciliación de archivos fantasma (DB≠Storage).

Ejecuta periódicamente (cada 6 horas por defecto):
1. Identifica input_files activos sin objeto en storage.objects
2. Archiva los registros huérfanos (is_active=false, is_archived=true)
3. Logging robusto de métricas

SSOT: usa public.projects.auth_user_id (NO owner_id)
SQL: usa bindparam(expanding=True) para compatibilidad asyncpg

Configuración por env vars:
- FILES_RECONCILE_GHOSTS_ENABLED: "true"/"false" (default: true)
- FILES_RECONCILE_GHOSTS_INTERVAL_HOURS: int (default: 6)
- FILES_RECONCILE_GHOSTS_BATCH_SIZE: int (default: 500)

Autor: DoxAI Team
Fecha: 2026-01-22
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Set
from uuid import UUID

from sqlalchemy import text, bindparam
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import SessionLocal
from app.shared.config import settings
from app.shared.observability import JobExecutionTracker

_logger = logging.getLogger("files.jobs.reconcile_ghost_files")

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════════════════════
JOB_ID = "files_reconcile_storage_ghosts"

def _env_bool(name: str, default: bool) -> bool:
    """Lee un booleano desde env de forma robusta."""
    raw = os.getenv(name)
    if raw is None:
        return default
    v = raw.strip().lower()
    return v in ("1", "true", "t", "yes", "y", "on")


def _env_int(name: str, default: int) -> int:
    """Lee un int desde env de forma robusta."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


# Configuración desde env vars
FILES_RECONCILE_GHOSTS_ENABLED = _env_bool("FILES_RECONCILE_GHOSTS_ENABLED", True)
FILES_RECONCILE_GHOSTS_INTERVAL_HOURS = _env_int("FILES_RECONCILE_GHOSTS_INTERVAL_HOURS", 6)
FILES_RECONCILE_GHOSTS_BATCH_SIZE = _env_int("FILES_RECONCILE_GHOSTS_BATCH_SIZE", 500)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

async def _check_storage_objects_access(db: AsyncSession, bucket: str) -> bool:
    """
    Verifica si storage.objects es accesible desde el rol actual.
    Returns True si accesible, False si no.
    """
    try:
        result = await db.execute(
            text("SELECT 1 FROM storage.objects WHERE bucket_id = :bucket LIMIT 1"),
            {"bucket": bucket}
        )
        result.fetchone()
        return True
    except Exception as e:
        _logger.warning(
            "reconcile_job_storage_access_failed: bucket=%s error=%s",
            bucket, str(e)[:200]
        )
        return False


async def _get_active_input_files_batch(
    db: AsyncSession,
    batch_size: int,
    offset: int = 0
) -> List[tuple]:
    """
    Obtiene un batch de input_files activos con storage_path.
    
    Returns:
        Lista de (input_file_id, input_file_storage_path, project_id)
    """
    result = await db.execute(
        text("""
            SELECT input_file_id, input_file_storage_path, project_id
            FROM public.input_files
            WHERE input_file_is_active = true
            AND input_file_is_archived = false
            AND input_file_storage_path IS NOT NULL
            ORDER BY input_file_id
            LIMIT :limit OFFSET :offset
        """),
        {"limit": batch_size, "offset": offset}
    )
    return result.fetchall()


async def _check_paths_exist_in_storage(
    db: AsyncSession,
    bucket: str,
    paths: List[str]
) -> Set[str]:
    """
    Verifica qué paths existen en storage.objects.
    
    Returns:
        Set de paths que SÍ existen en storage.
    """
    if not paths:
        return set()
    
    # Usar IN :paths con bindparam(expanding=True) para compatibilidad asyncpg
    sql = text("""
        SELECT name 
        FROM storage.objects 
        WHERE bucket_id = :bucket
        AND name IN :paths
    """).bindparams(
        bindparam("bucket"),
        bindparam("paths", expanding=True)
    )
    
    result = await db.execute(sql, {"bucket": bucket, "paths": paths})
    return {row[0] for row in result.fetchall()}


async def _archive_ghost_files(
    db: AsyncSession,
    ghost_file_ids: List[UUID]
) -> int:
    """
    Archiva archivos fantasma.
    
    IMPORTANTE: ghost_file_ids debe ser List[UUID], NO strings.
    
    Returns:
        Número de archivos archivados.
    """
    if not ghost_file_ids:
        return 0
    
    # ghost_file_ids ya son UUID, NO convertir a str
    archive_sql = text("""
        UPDATE public.input_files
        SET input_file_is_active = false,
            input_file_is_archived = true,
            updated_at = now()
        WHERE input_file_id IN :ids
    """).bindparams(
        bindparam("ids", expanding=True)
    )
    
    await db.execute(archive_sql, {"ids": ghost_file_ids})
    return len(ghost_file_ids)


# ═══════════════════════════════════════════════════════════════════════════════
# JOB PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

async def reconcile_ghost_files_job(
    batch_size: int | None = None,
) -> Dict[str, Any]:
    """
    Job principal de reconciliación de archivos fantasma.
    
    Flujo:
    1. Verificar acceso a storage.objects
    2. Iterar por batches de input_files activos
    3. Para cada batch, verificar existencia en storage
    4. Archivar los que no existen
    5. Logging de métricas
    
    Args:
        batch_size: Tamaño de batch (default: desde env var)
    
    Returns:
        Dict con estadísticas del job
    """
    # Usar batch_size de env var si no se especifica
    if batch_size is None:
        batch_size = FILES_RECONCILE_GHOSTS_BATCH_SIZE
    
    start_time = datetime.utcnow()
    bucket_name = getattr(settings, 'supabase_bucket_name', 'users-files')
    
    stats: Dict[str, Any] = {
        "job_id": JOB_ID,
        "timestamp": start_time.isoformat(),
        "total_scanned": 0,
        "ghosts_found": 0,
        "ghosts_archived": 0,
        "batches_processed": 0,
        "affected_project_ids": [],
        "storage_accessible": False,
        "error": None,
    }
    
    _logger.info(
        "reconcile_ghost_files_job_start: bucket=%s batch_size=%d",
        bucket_name, batch_size
    )
    
    try:
        async with SessionLocal() as db:
            # Track job execution
            tracker = JobExecutionTracker(
                db=db,
                job_id=JOB_ID,
                job_type="scheduler",
                module="files",
            )
            await tracker.start()
            
            try:
                # 1. Verificar acceso a storage.objects
                storage_accessible = await _check_storage_objects_access(db, bucket_name)
                stats["storage_accessible"] = storage_accessible
                
                if not storage_accessible:
                    _logger.warning(
                        "reconcile_ghost_files_job_skip: storage.objects not accessible"
                    )
                    stats["error"] = "STORAGE_OBJECTS_UNAVAILABLE"
                    await tracker.finish_failed("STORAGE_OBJECTS_UNAVAILABLE", stats)
                    return stats
                
                # 2. Procesar por batches
                offset = 0
                affected_projects: Set[str] = set()
                
                while True:
                    # Obtener batch de archivos activos
                    batch = await _get_active_input_files_batch(db, batch_size, offset)
                    
                    if not batch:
                        break
                    
                    stats["batches_processed"] += 1
                    stats["total_scanned"] += len(batch)
                    
                    # Extraer paths para verificar
                    paths = [row[1] for row in batch if row[1]]
                    
                    if not paths:
                        offset += batch_size
                        continue
                    
                    # Verificar existencia en storage
                    try:
                        existing_paths = await _check_paths_exist_in_storage(
                            db, bucket_name, paths
                        )
                    except Exception as storage_err:
                        _logger.error(
                            "reconcile_ghost_files_batch_storage_error: batch=%d error=%s",
                            stats["batches_processed"],
                            str(storage_err)[:200]
                        )
                        offset += batch_size
                        continue
                    
                    # Identificar fantasmas
                    ghost_files = [
                        (row[0], row[2])  # (input_file_id, project_id)
                        for row in batch
                        if row[1] not in existing_paths
                    ]
                    
                    if ghost_files:
                        ghost_ids = [gf[0] for gf in ghost_files]
                        project_ids = [str(gf[1])[:8] for gf in ghost_files]
                        
                        # Archivar fantasmas
                        archived_count = await _archive_ghost_files(db, ghost_ids)
                        
                        stats["ghosts_found"] += len(ghost_files)
                        stats["ghosts_archived"] += archived_count
                        affected_projects.update(project_ids)
                        
                        _logger.info(
                            "reconcile_ghost_files_batch: batch=%d ghosts=%d archived=%d",
                            stats["batches_processed"],
                            len(ghost_files),
                            archived_count
                        )
                    
                    offset += batch_size
                
                # Commit al final de todos los batches
                await db.commit()
                
                # Limitar project_ids en el log (primeros 10)
                stats["affected_project_ids"] = list(affected_projects)[:10]
                
                # Track success
                await tracker.finish_success({
                    "total_scanned": stats["total_scanned"],
                    "ghosts_found": stats["ghosts_found"],
                    "ghosts_archived": stats["ghosts_archived"],
                })
                
            except Exception as inner_e:
                # Track failure
                _logger.error(
                    "reconcile_ghost_files_job_inner_error: %s",
                    str(inner_e)[:200],
                    exc_info=True
                )
                await tracker.finish_failed(str(inner_e)[:500], stats)
                raise
            
    except Exception as e:
        _logger.error(
            "reconcile_ghost_files_job_error: %s",
            str(e),
            exc_info=True
        )
        stats["error"] = str(e)[:200]
    
    # Calcular duración
    end_time = datetime.utcnow()
    duration_ms = (end_time - start_time).total_seconds() * 1000
    stats["duration_ms"] = round(duration_ms, 2)
    
    _logger.info(
        "reconcile_ghost_files_job_done: scanned=%d ghosts_found=%d archived=%d "
        "batches=%d duration_ms=%.2f projects_affected=%d",
        stats["total_scanned"],
        stats["ghosts_found"],
        stats["ghosts_archived"],
        stats["batches_processed"],
        stats["duration_ms"],
        len(stats["affected_project_ids"]),
    )
    
    return stats


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRO EN SCHEDULER
# ═══════════════════════════════════════════════════════════════════════════════

def register_reconcile_ghost_files_job(
    scheduler=None,
) -> str | None:
    """
    Registra el job de reconciliación de archivos fantasma en el scheduler.
    
    Sigue el patrón canónico:
    - Si no se pasa scheduler, usa get_scheduler()
    - Configurable por env vars (FILES_RECONCILE_GHOSTS_*)
    - Retorna None si el job está deshabilitado
    
    Args:
        scheduler: Instancia de SchedulerService (opcional, usa global si None)
    
    Returns:
        ID del job registrado, o None si está deshabilitado
    """
    # Verificar si está habilitado
    if not FILES_RECONCILE_GHOSTS_ENABLED:
        _logger.info(
            "[reconcile_ghost_files] Job disabled (FILES_RECONCILE_GHOSTS_ENABLED=false)"
        )
        return None
    
    # Usar scheduler global si no se pasa uno
    if scheduler is None:
        from app.shared.scheduler import get_scheduler
        scheduler = get_scheduler()
    
    # Leer intervalo desde env var
    hours = FILES_RECONCILE_GHOSTS_INTERVAL_HOURS
    
    job_id = scheduler.add_interval_job(
        func=reconcile_ghost_files_job,
        job_id=JOB_ID,
        hours=hours,
        minutes=0,
        seconds=0,
    )
    
    _logger.info(
        "[reconcile_ghost_files] Job '%s' registered: every %d hours (batch_size=%d)",
        JOB_ID, hours, FILES_RECONCILE_GHOSTS_BATCH_SIZE
    )
    
    return job_id


__all__ = [
    "JOB_ID",
    "reconcile_ghost_files_job",
    "register_reconcile_ghost_files_job",
    "FILES_RECONCILE_GHOSTS_ENABLED",
    "FILES_RECONCILE_GHOSTS_INTERVAL_HOURS",
    "FILES_RECONCILE_GHOSTS_BATCH_SIZE",
]

# Fin del archivo
