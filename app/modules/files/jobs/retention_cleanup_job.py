# -*- coding: utf-8 -*-
"""
backend/app/modules/files/jobs/retention_cleanup_job.py

Job automático para política de retención de archivos.

Ejecuta periódicamente (cada 24 horas por defecto):
1. Transiciona proyectos closed → retention_grace tras umbral
2. Transiciona proyectos retention_grace → deleted_by_policy tras umbral
3. Elimina archivos físicos de Supabase Storage (API, no SQL)
4. Invalida registros en DB (sin borrar histórico)
5. Logging robusto de métricas y auditoría

SSOT DB-first (sin columnas nuevas):
- projects.status: closed | retention_grace | deleted_by_policy
  (Columna canónica, NO project_status)
- projects.ready_at: timestamp canónico para inicio de retención
- input_files.storage_state: present → missing (invalidación lógica)
- product_files.storage_state: present → missing (invalidación lógica)

Configuración por env vars:
- FILES_RETENTION_ENABLED: "true"/"false" (default: true)
- FILES_RETENTION_INTERVAL_HOURS: int (default: 24)
- FILES_RETENTION_GRACE_DAYS: días hasta retention_grace (default: 30)
- FILES_RETENTION_DELETE_DAYS: días hasta eliminación (default: 60)
- FILES_RETENTION_BATCH_SIZE: int (default: 100)

Autor: DoxAI Team
Fecha: 2026-01-26
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import text, bindparam
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import SessionLocal
from app.shared.config import settings
from app.shared.observability import JobExecutionTracker

_logger = logging.getLogger("files.jobs.retention_cleanup")

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════════════════════
JOB_ID = "files_retention_cleanup"


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
FILES_RETENTION_ENABLED = _env_bool("FILES_RETENTION_ENABLED", True)
FILES_RETENTION_INTERVAL_HOURS = _env_int("FILES_RETENTION_INTERVAL_HOURS", 24)
FILES_RETENTION_GRACE_DAYS = _env_int("FILES_RETENTION_GRACE_DAYS", 30)
FILES_RETENTION_DELETE_DAYS = _env_int("FILES_RETENTION_DELETE_DAYS", 60)
FILES_RETENTION_BATCH_SIZE = _env_int("FILES_RETENTION_BATCH_SIZE", 100)


# ═══════════════════════════════════════════════════════════════════════════════
# STORAGE CLIENT (Supabase Storage API)
# ═══════════════════════════════════════════════════════════════════════════════

def _get_storage_client():
    """
    Obtiene el cliente de Supabase Storage HTTP.
    Lazy import para evitar problemas de inicialización.
    """
    from app.shared.utils.http_storage_client import get_http_storage_client
    return get_http_storage_client()


async def _delete_file_from_storage(bucket: str, path: str) -> Dict[str, Any]:
    """
    Elimina un archivo de Supabase Storage usando la API HTTP.
    
    Returns:
        Dict con resultado: {"success": bool, "not_found": bool, "error": str|None}
    """
    try:
        client = _get_storage_client()
        await client.delete_file(bucket, path)
        return {"success": True, "not_found": False, "error": None}
    except FileNotFoundError:
        # Archivo ya no existe - tratar como éxito (idempotencia)
        _logger.debug("retention_storage_delete_not_found: path=%s", path[:50])
        return {"success": True, "not_found": True, "error": None}
    except Exception as e:
        _logger.warning(
            "retention_storage_delete_error: path=%s error=%s",
            path[:50], str(e)[:100]
        )
        return {"success": False, "not_found": False, "error": str(e)[:200]}


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

async def _get_projects_for_grace_transition(
    db: AsyncSession,
    grace_threshold: datetime,
    batch_size: int,
) -> List[Tuple[UUID, datetime]]:
    """
    Obtiene proyectos closed que deben pasar a retention_grace.
    
    Criterio: status='closed' AND ready_at < grace_threshold
    
    Usa ready_at como timestamp canónico (no columnas nuevas).
    SSOT: columna es "status", no "project_status".
    
    Returns:
        Lista de (project_id, ready_at)
    """
    result = await db.execute(
        text("""
            SELECT id, ready_at
            FROM public.projects
            WHERE status = 'closed'
              AND ready_at IS NOT NULL
              AND ready_at < :threshold
            ORDER BY ready_at ASC
            LIMIT :limit
        """),
        {"threshold": grace_threshold, "limit": batch_size}
    )
    return [(row[0], row[1]) for row in result.fetchall()]


async def _get_projects_for_deletion(
    db: AsyncSession,
    delete_threshold: datetime,
    batch_size: int,
) -> List[Tuple[UUID, datetime]]:
    """
    Obtiene proyectos retention_grace que deben pasar a deleted_by_policy.
    
    Criterio: status='retention_grace' AND ready_at < delete_threshold
    
    Nota: Usamos ready_at porque es el único timestamp canónico disponible.
    El tiempo total desde ready → deleted_by_policy es (grace_days + delete_days).
    SSOT: columna es "status", no "project_status".
    
    Returns:
        Lista de (project_id, ready_at)
    """
    result = await db.execute(
        text("""
            SELECT id, ready_at
            FROM public.projects
            WHERE status = 'retention_grace'
              AND ready_at IS NOT NULL
              AND ready_at < :threshold
            ORDER BY ready_at ASC
            LIMIT :limit
        """),
        {"threshold": delete_threshold, "limit": batch_size}
    )
    return [(row[0], row[1]) for row in result.fetchall()]


async def _transition_to_retention_grace(
    db: AsyncSession,
    project_ids: List[UUID],
) -> int:
    """
    Transiciona proyectos a retention_grace.
    SSOT: columna es "status", no "project_status".
    
    Returns:
        Número de proyectos actualizados.
    """
    if not project_ids:
        return 0
    
    sql = text("""
        UPDATE public.projects
        SET status = 'retention_grace',
            updated_at = now()
        WHERE id IN :ids
    """).bindparams(bindparam("ids", expanding=True))
    
    await db.execute(sql, {"ids": project_ids})
    return len(project_ids)


async def _get_files_for_project(
    db: AsyncSession,
    project_id: UUID,
) -> Dict[str, List[Tuple[UUID, str]]]:
    """
    Obtiene archivos activos de un proyecto.
    
    Returns:
        Dict con 'input' y 'product' lists de (file_id, storage_path)
    """
    result_input = await db.execute(
        text("""
            SELECT input_file_id, input_file_storage_path
            FROM public.input_files
            WHERE project_id = :project_id
              AND storage_state = 'present'
        """),
        {"project_id": project_id}
    )
    
    result_product = await db.execute(
        text("""
            SELECT product_file_id, product_file_storage_path
            FROM public.product_files
            WHERE project_id = :project_id
              AND storage_state = 'present'
        """),
        {"project_id": project_id}
    )
    
    return {
        "input": [(row[0], row[1]) for row in result_input.fetchall()],
        "product": [(row[0], row[1]) for row in result_product.fetchall()],
    }


async def _delete_files_from_storage_batch(
    bucket: str,
    paths: List[str],
) -> Dict[str, Any]:
    """
    Elimina múltiples archivos del storage usando la API HTTP.
    
    Returns:
        Dict con estadísticas de eliminación
    """
    if not paths:
        return {"deleted": 0, "errors": 0, "not_found": 0}
    
    deleted = 0
    errors = 0
    not_found = 0
    
    for path in paths:
        result = await _delete_file_from_storage(bucket, path)
        if result["success"]:
            if result["not_found"]:
                not_found += 1
            else:
                deleted += 1
        else:
            errors += 1
    
    return {"deleted": deleted, "errors": errors, "not_found": not_found}


async def _invalidate_files_in_db(
    db: AsyncSession,
    input_file_ids: List[UUID],
    product_file_ids: List[UUID],
    reason: str,
) -> Dict[str, int]:
    """
    Invalida archivos en DB (marca storage_state='missing').
    
    NO elimina registros, preserva histórico.
    
    Returns:
        Dict con contadores por tipo.
    """
    result = {"input": 0, "product": 0}
    
    if input_file_ids:
        sql = text("""
            UPDATE public.input_files
            SET storage_state = 'missing',
                invalidated_at = now(),
                invalidation_reason = :reason,
                input_file_is_active = false,
                updated_at = now()
            WHERE input_file_id IN :ids
        """).bindparams(bindparam("ids", expanding=True))
        
        await db.execute(sql, {"ids": input_file_ids, "reason": reason})
        result["input"] = len(input_file_ids)
    
    if product_file_ids:
        sql = text("""
            UPDATE public.product_files
            SET storage_state = 'missing',
                invalidated_at = now(),
                invalidation_reason = :reason,
                product_file_is_active = false,
                updated_at = now()
            WHERE product_file_id IN :ids
        """).bindparams(bindparam("ids", expanding=True))
        
        await db.execute(sql, {"ids": product_file_ids, "reason": reason})
        result["product"] = len(product_file_ids)
    
    return result


async def _transition_to_deleted_by_policy(
    db: AsyncSession,
    project_id: UUID,
) -> None:
    """
    Marca un proyecto como deleted_by_policy.
    SSOT: columna es "status", no "project_status".
    """
    await db.execute(
        text("""
            UPDATE public.projects
            SET status = 'deleted_by_policy',
                updated_at = now()
            WHERE id = :project_id
        """),
        {"project_id": project_id}
    )


async def _log_retention_action(
    db: AsyncSession,
    project_id: UUID,
    auth_user_id: UUID,
    action_type: str,
    action_details: str,
    action_metadata: dict,
) -> None:
    """
    Registra una acción de retención en project_action_logs.
    
    Usa action_type='updated' para transiciones de retención.
    """
    await db.execute(
        text("""
            INSERT INTO public.project_action_logs
            (project_id, auth_user_id, action_type, action_details, action_metadata)
            VALUES (:project_id, :auth_user_id, :action_type, :details, :metadata)
        """),
        {
            "project_id": project_id,
            "auth_user_id": auth_user_id,
            "action_type": action_type,
            "details": action_details,
            "metadata": action_metadata,
        }
    )


async def _log_retention_notification(
    db: AsyncSession,
    project_id: UUID,
    notification_type: str,
) -> None:
    """
    Registra una notificación de retención en project_action_logs.
    
    Stub para futuras integraciones de email/banner.
    Registra en action_metadata para que UI pueda mostrar banner.
    """
    # Obtener auth_user_id del proyecto para el log
    result = await db.execute(
        text("SELECT auth_user_id FROM public.projects WHERE id = :pid"),
        {"pid": project_id}
    )
    row = result.fetchone()
    if not row:
        _logger.warning(
            "retention_notification_skip: project_id=%s not_found",
            str(project_id)[:8]
        )
        return
    
    auth_user_id = row[0]
    
    # Calcular fecha estimada de eliminación
    from datetime import timedelta
    estimated_deletion = datetime.utcnow() + timedelta(days=FILES_RETENTION_DELETE_DAYS)
    
    await _log_retention_action(
        db,
        project_id=project_id,
        auth_user_id=auth_user_id,
        action_type="updated",
        action_details=f"retention_{notification_type}",
        action_metadata={
            "retention_event": notification_type,
            "notification_pending": True,
            "estimated_deletion_at": estimated_deletion.isoformat(),
            "grace_days": FILES_RETENTION_GRACE_DAYS,
            "delete_days": FILES_RETENTION_DELETE_DAYS,
        },
    )
    
    _logger.info(
        "retention_notification: project_id=%s type=%s estimated_deletion=%s",
        str(project_id)[:8],
        notification_type,
        estimated_deletion.date().isoformat(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# JOB PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

async def retention_cleanup_job(
    dry_run: bool = False,
    batch_size: Optional[int] = None,
    grace_days: Optional[int] = None,
    delete_days: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Job principal de retención de archivos.
    
    Flujo:
    1. Transicionar closed → retention_grace (umbral: grace_days desde ready_at)
    2. Para proyectos retention_grace pasado delete_days desde ready_at:
       a. Eliminar archivos de storage (API HTTP)
       b. Invalidar registros en DB
       c. Transicionar a deleted_by_policy
    
    Args:
        dry_run: Si True, solo simula sin modificar datos
        batch_size: Proyectos a procesar por batch (default: desde env)
        grace_days: Días hasta retention_grace (default: desde env)
        delete_days: Días hasta eliminación (default: desde env)
    
    Returns:
        Dict con estadísticas del job
    """
    # Usar defaults de env vars si no se especifican
    if batch_size is None:
        batch_size = FILES_RETENTION_BATCH_SIZE
    if grace_days is None:
        grace_days = FILES_RETENTION_GRACE_DAYS
    if delete_days is None:
        delete_days = FILES_RETENTION_DELETE_DAYS
    
    start_time = datetime.utcnow()
    bucket_name = getattr(settings, 'supabase_bucket_name', 'users-files')
    
    # Calcular thresholds
    # grace_threshold: proyectos closed con ready_at anterior pasan a grace
    # delete_threshold: proyectos en grace con ready_at anterior se eliminan
    # El tiempo total es grace_days + delete_days desde ready_at
    now = datetime.utcnow()
    grace_threshold = now - timedelta(days=grace_days)
    delete_threshold = now - timedelta(days=grace_days + delete_days)
    
    stats: Dict[str, Any] = {
        "job_id": JOB_ID,
        "timestamp": start_time.isoformat(),
        "dry_run": dry_run,
        "config": {
            "grace_days": grace_days,
            "delete_days": delete_days,
            "batch_size": batch_size,
            "grace_threshold": grace_threshold.isoformat(),
            "delete_threshold": delete_threshold.isoformat(),
        },
        # Grace transition stats
        "projects_to_grace": 0,
        "projects_transitioned_to_grace": 0,
        # Deletion stats
        "projects_to_delete": 0,
        "projects_deleted_by_policy": 0,
        "files_deleted_storage": 0,
        "files_not_found_storage": 0,
        "files_invalidated_db": 0,
        "storage_errors": 0,
        # Meta
        "error": None,
    }
    
    _logger.info(
        "retention_cleanup_job_start: dry_run=%s grace_days=%d delete_days=%d batch=%d",
        dry_run, grace_days, delete_days, batch_size
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
                # ───────────────────────────────────────────────────────────
                # FASE 1: Transición closed → retention_grace
                # ───────────────────────────────────────────────────────────
                grace_projects = await _get_projects_for_grace_transition(
                    db, grace_threshold, batch_size
                )
                stats["projects_to_grace"] = len(grace_projects)
                
                if grace_projects:
                    project_ids = [p[0] for p in grace_projects]
                    
                    if not dry_run:
                        await _transition_to_retention_grace(db, project_ids)
                        stats["projects_transitioned_to_grace"] = len(project_ids)
                        
                        # Log notification stub para cada proyecto
                        for pid in project_ids:
                            await _log_retention_notification(
                                db, pid, "entering_retention_grace"
                            )
                    
                    _logger.info(
                        "retention_cleanup_grace_transition: count=%d dry_run=%s",
                        len(project_ids), dry_run
                    )
                
                # ───────────────────────────────────────────────────────────
                # FASE 2: Eliminación por política (con savepoints por proyecto)
                # ───────────────────────────────────────────────────────────
                delete_projects = await _get_projects_for_deletion(
                    db, delete_threshold, batch_size
                )
                stats["projects_to_delete"] = len(delete_projects)
                
                for project_id, _ in delete_projects:
                    # PROD-SAFE: Crear savepoint por proyecto para aislar errores
                    savepoint_name = f"sp_retention_{str(project_id)[:8]}"
                    
                    try:
                        if not dry_run:
                            await db.execute(text(f"SAVEPOINT {savepoint_name}"))
                        
                        # Obtener archivos del proyecto
                        files = await _get_files_for_project(db, project_id)
                        
                        all_input_ids = [f[0] for f in files["input"]]
                        all_product_ids = [f[0] for f in files["product"]]
                        all_paths = (
                            [f[1] for f in files["input"]] +
                            [f[1] for f in files["product"]]
                        )
                        
                        if not dry_run:
                            # Eliminar de storage usando API HTTP
                            storage_result = await _delete_files_from_storage_batch(
                                bucket_name, all_paths
                            )
                            stats["files_deleted_storage"] += storage_result["deleted"]
                            stats["files_not_found_storage"] += storage_result["not_found"]
                            stats["storage_errors"] += storage_result["errors"]
                            
                            # Solo invalidar si no hubo errores de storage
                            # (archivos no encontrados son OK - idempotencia)
                            if storage_result["errors"] == 0:
                                invalidate_result = await _invalidate_files_in_db(
                                    db,
                                    all_input_ids,
                                    all_product_ids,
                                    reason=f"retention_policy_delete_days_{delete_days}"
                                )
                                stats["files_invalidated_db"] += (
                                    invalidate_result["input"] + invalidate_result["product"]
                                )
                                
                                # Marcar proyecto como deleted_by_policy
                                await _transition_to_deleted_by_policy(db, project_id)
                                stats["projects_deleted_by_policy"] += 1
                                
                                # PROD-SAFE: Release savepoint tras éxito
                                await db.execute(text(f"RELEASE SAVEPOINT {savepoint_name}"))
                            else:
                                # Rollback savepoint por errores de storage
                                await db.execute(text(f"ROLLBACK TO SAVEPOINT {savepoint_name}"))
                                _logger.warning(
                                    "retention_cleanup_partial_failure: project_id=%s errors=%d rolled_back=true",
                                    str(project_id)[:8],
                                    storage_result["errors"]
                                )
                        else:
                            # dry_run: simular conteos
                            stats["files_deleted_storage"] += len(all_paths)
                            stats["files_invalidated_db"] += len(all_input_ids) + len(all_product_ids)
                            stats["projects_deleted_by_policy"] += 1
                        
                        _logger.info(
                            "retention_cleanup_project: project_id=%s files=%d dry_run=%s",
                            str(project_id)[:8],
                            len(all_paths),
                            dry_run
                        )
                        
                    except Exception as project_error:
                        # PROD-SAFE: Rollback savepoint y continuar con el siguiente proyecto
                        if not dry_run:
                            try:
                                await db.execute(text(f"ROLLBACK TO SAVEPOINT {savepoint_name}"))
                            except Exception:
                                pass  # Savepoint puede no existir si falló antes
                        
                        _logger.error(
                            "retention_cleanup_project_error: project_id=%s error=%s rolled_back=true",
                            str(project_id)[:8],
                            str(project_error)[:200]
                        )
                        # Continue con el siguiente proyecto
                        continue
                
                # Commit al final del batch
                if not dry_run:
                    await db.commit()
                
                # Track success
                await tracker.finish_success({
                    "projects_to_grace": stats["projects_to_grace"],
                    "projects_deleted": stats["projects_deleted_by_policy"],
                    "files_deleted": stats["files_deleted_storage"],
                    "dry_run": dry_run,
                })
                
            except Exception as inner_e:
                _logger.error(
                    "retention_cleanup_job_inner_error: %s",
                    str(inner_e)[:200],
                    exc_info=True
                )
                await tracker.finish_failed(str(inner_e)[:500], stats)
                raise
            
    except Exception as e:
        _logger.error(
            "retention_cleanup_job_error: %s",
            str(e),
            exc_info=True
        )
        stats["error"] = str(e)[:200]
    
    # Calcular duración
    end_time = datetime.utcnow()
    duration_ms = (end_time - start_time).total_seconds() * 1000
    stats["duration_ms"] = round(duration_ms, 2)
    
    _logger.info(
        "retention_cleanup_job_done: grace=%d deleted=%d files=%d errors=%d "
        "duration_ms=%.2f dry_run=%s",
        stats["projects_transitioned_to_grace"],
        stats["projects_deleted_by_policy"],
        stats["files_deleted_storage"],
        stats["storage_errors"],
        stats["duration_ms"],
        dry_run,
    )
    
    return stats


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRO EN SCHEDULER
# ═══════════════════════════════════════════════════════════════════════════════

def register_retention_cleanup_job(
    scheduler=None,
) -> Optional[str]:
    """
    Registra el job de retención en el scheduler.
    
    Args:
        scheduler: Instancia de SchedulerService (opcional, usa global si None)
    
    Returns:
        ID del job registrado, o None si está deshabilitado
    """
    if not FILES_RETENTION_ENABLED:
        _logger.info(
            "[retention_cleanup] Job disabled (FILES_RETENTION_ENABLED=false)"
        )
        return None
    
    if scheduler is None:
        from app.shared.scheduler import get_scheduler
        scheduler = get_scheduler()
    
    hours = FILES_RETENTION_INTERVAL_HOURS
    
    job_id = scheduler.add_interval_job(
        func=retention_cleanup_job,
        job_id=JOB_ID,
        hours=hours,
        minutes=0,
        seconds=0,
    )
    
    _logger.info(
        "[retention_cleanup] Job '%s' registered: every %d hours "
        "(grace_days=%d, delete_days=%d)",
        JOB_ID, hours,
        FILES_RETENTION_GRACE_DAYS,
        FILES_RETENTION_DELETE_DAYS
    )
    
    return job_id


__all__ = [
    "JOB_ID",
    "retention_cleanup_job",
    "register_retention_cleanup_job",
    "FILES_RETENTION_ENABLED",
    "FILES_RETENTION_INTERVAL_HOURS",
    "FILES_RETENTION_GRACE_DAYS",
    "FILES_RETENTION_DELETE_DAYS",
    "FILES_RETENTION_BATCH_SIZE",
]
