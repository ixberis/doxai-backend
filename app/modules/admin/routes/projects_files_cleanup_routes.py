# -*- coding: utf-8 -*-
"""
backend/app/modules/admin/routes/projects_files_cleanup_routes.py

Admin endpoints for manual cleanup operations (OPERACIÓN / Cleanup).

Implements safe, audited cleanup with:
- Dry-run mandatory
- Explicit text confirmation
- Rate limiting (10 min per type) - FAIL-CLOSED
- Job execution tracking
- Transaction-based (all-or-nothing)
- Deterministic batches (ORDER BY)

Endpoints:
- POST /_internal/admin/projects-files/operational/cleanup/ghost-files/dry-run
- POST /_internal/admin/projects-files/operational/cleanup/ghost-files
- POST /_internal/admin/projects-files/operational/cleanup/storage-snapshots/dry-run
- POST /_internal/admin/projects-files/operational/cleanup/storage-snapshots

Author: DoxAI
Created: 2026-01-23
"""
import logging
from datetime import datetime, timedelta, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.modules.auth.dependencies import require_admin_strict
from app.shared.observability import JobExecutionTracker


logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

MAX_RECORDS_PER_RUN = 5000
RATE_LIMIT_MINUTES = 10

# Confirmation texts
REQUIRED_CONFIRM_TEXT_GHOST = "CONFIRMAR LIMPIEZA"
REQUIRED_CONFIRM_TEXT_SNAPSHOTS = "CONFIRMAR LIMPIEZA SNAPSHOTS"

# Snapshot retention limits
MIN_RETENTION_DAYS = 30
MAX_RETENTION_DAYS = 365
DEFAULT_RETENTION_DAYS = 180


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS - Ghost Files
# ═══════════════════════════════════════════════════════════════════════════════

class DryRunResponse(BaseModel):
    """Response from dry-run operation (ghost files)."""
    eligible_count: int = Field(..., description="Number of records that would be deleted")
    estimated_batches: int = Field(..., description="Estimated number of runs needed")
    max_per_run: int = Field(MAX_RECORDS_PER_RUN, description="Maximum records per execution")
    rate_limit_minutes: int = Field(RATE_LIMIT_MINUTES, description="Minutes between cleanups")
    can_execute: bool = Field(..., description="Whether execution is allowed (rate limit)")
    next_allowed_at: Optional[str] = Field(None, description="When next cleanup is allowed")


class CleanupRequest(BaseModel):
    """Request body for ghost files cleanup execution."""
    confirm_text: str = Field(..., description="Must be exactly 'CONFIRMAR LIMPIEZA'")


class CleanupResponse(BaseModel):
    """Response from cleanup execution."""
    deleted_count: int = Field(..., description="Number of records deleted")
    execution_id: str = Field(..., description="Job execution ID for audit trail")
    duration_ms: int = Field(..., description="Execution time in milliseconds")
    remaining: int = Field(..., description="Remaining records after this run")
    message: str = Field(..., description="Human-readable result message")


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS - Storage Snapshots
# ═══════════════════════════════════════════════════════════════════════════════

class SnapshotsDryRunResponse(BaseModel):
    """Response from dry-run operation (storage snapshots)."""
    eligible_count: int = Field(..., description="Number of snapshot rows that would be deleted")
    cutoff_day: str = Field(..., description="Snapshots before this date are eligible (YYYY-MM-DD)")
    estimated_batches: int = Field(..., description="Estimated number of runs needed")
    max_per_run: int = Field(MAX_RECORDS_PER_RUN, description="Maximum records per execution")
    rate_limit_minutes: int = Field(RATE_LIMIT_MINUTES, description="Minutes between cleanups")
    can_execute: bool = Field(..., description="Whether execution is allowed (rate limit)")
    next_allowed_at: Optional[str] = Field(None, description="When next cleanup is allowed")
    retention_days: int = Field(..., description="Retention days used for calculation")


class SnapshotsCleanupRequest(BaseModel):
    """Request body for storage snapshots cleanup execution."""
    confirm_text: str = Field(..., description="Must be exactly 'CONFIRMAR LIMPIEZA SNAPSHOTS'")
    retention_days: int = Field(DEFAULT_RETENTION_DAYS, description="Days to retain (30-365)")
    
    @field_validator('retention_days')
    @classmethod
    def validate_retention(cls, v: int) -> int:
        if v < MIN_RETENTION_DAYS:
            raise ValueError(f"retention_days must be at least {MIN_RETENTION_DAYS}")
        if v > MAX_RETENTION_DAYS:
            raise ValueError(f"retention_days must be at most {MAX_RETENTION_DAYS}")
        return v


class SnapshotsCleanupResponse(BaseModel):
    """Response from storage snapshots cleanup execution."""
    deleted_count: int = Field(..., description="Number of snapshot rows deleted")
    remaining: int = Field(..., description="Remaining old snapshots after this run")
    cutoff_day: str = Field(..., description="Snapshots before this date were deleted")
    execution_id: str = Field(..., description="Job execution ID for audit trail")
    duration_ms: int = Field(..., description="Execution time in milliseconds")
    message: str = Field(..., description="Human-readable result message")


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS - Shared
# ═══════════════════════════════════════════════════════════════════════════════

async def check_rate_limit(db: AsyncSession, job_id: str) -> tuple[bool, Optional[datetime]]:
    """
    Check if rate limit allows execution.
    
    FAIL-CLOSED: If rate limit check fails (table missing, DB error), 
    cleanup is NOT allowed. This is a destructive operation that requires auditing.
    
    Returns:
        (can_execute, next_allowed_at)
    
    Raises:
        HTTPException(500) if rate limit check fails (fail-closed security)
    """
    q = text("""
        SELECT started_at
        FROM kpis.job_executions
        WHERE job_id = :job_id
          AND status IN ('success', 'running')
        ORDER BY started_at DESC
        LIMIT 1
    """)
    
    # FAIL-CLOSED: Any error prevents execution (no silent fallback)
    try:
        res = await db.execute(q, {"job_id": job_id})
        row = res.fetchone()
        
        if not row:
            return True, None
        
        last_run = row.started_at
        next_allowed = last_run + timedelta(minutes=RATE_LIMIT_MINUTES)
        
        if datetime.utcnow() >= next_allowed:
            return True, None
        
        return False, next_allowed
    except Exception as e:
        # FAIL-CLOSED: If we can't verify rate limit or audit table, deny execution
        logger.error(f"[cleanup] FAIL-CLOSED: Rate limit check failed (SSOT missing?): {e}")
        raise HTTPException(
            status_code=500,
            detail=f"SSOTMissingError: Cannot verify rate limit or audit table (kpis.job_executions). Cleanup denied. Error: {str(e)}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS - Ghost Files
# ═══════════════════════════════════════════════════════════════════════════════

async def count_ghost_files(db: AsyncSession) -> int:
    """
    Count ghost files eligible for cleanup.
    
    Condition:
    - input_file_is_active = true
    - storage_exists = false
    """
    q = text("""
        SELECT COUNT(*) AS cnt
        FROM public.input_files
        WHERE input_file_is_active = true
          AND storage_exists = false
    """)
    
    res = await db.execute(q)
    return int(res.scalar() or 0)


async def delete_ghost_files(db: AsyncSession, limit: int = MAX_RECORDS_PER_RUN) -> int:
    """
    Delete ghost files from input_files table.
    
    Uses a single transaction with LIMIT and ORDER BY for deterministic batches.
    
    Returns:
        Number of records deleted
    """
    # Subquery approach for safe deletion with LIMIT + ORDER BY for deterministic batches
    q = text("""
        DELETE FROM public.input_files
        WHERE input_file_id IN (
            SELECT input_file_id
            FROM public.input_files
            WHERE input_file_is_active = true
              AND storage_exists = false
            ORDER BY input_file_id
            LIMIT :limit
        )
    """)
    
    res = await db.execute(q, {"limit": limit})
    return res.rowcount or 0


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS - Storage Snapshots
# ═══════════════════════════════════════════════════════════════════════════════

async def verify_snapshots_table_exists(db: AsyncSession) -> None:
    """
    Verify kpis.storage_daily_snapshots table exists.
    
    FAIL-CLOSED: Raises HTTPException(500) if table doesn't exist.
    """
    q = text("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'kpis'
              AND table_name = 'storage_daily_snapshots'
        ) AS exists
    """)
    
    try:
        res = await db.execute(q)
        exists = res.scalar()
        
        if not exists:
            raise HTTPException(
                status_code=500,
                detail="SSOTMissingError: Table kpis.storage_daily_snapshots not found. Cleanup denied.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[cleanup] FAIL-CLOSED: Snapshots table check failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"SSOTMissingError: Cannot verify kpis.storage_daily_snapshots. Error: {str(e)}",
        )


async def count_old_snapshots(db: AsyncSession, retention_days: int) -> tuple[int, date]:
    """
    Count storage snapshots older than retention period.
    
    Args:
        retention_days: Days to retain (snapshots older than this are eligible)
    
    Returns:
        (eligible_count, cutoff_day)
    """
    q = text("""
        SELECT 
            COUNT(*) AS cnt,
            (CURRENT_DATE - make_interval(days => :retention_days))::date AS cutoff_day
        FROM kpis.storage_daily_snapshots
        WHERE day < CURRENT_DATE - make_interval(days => :retention_days)
    """)
    
    res = await db.execute(q, {"retention_days": retention_days})
    row = res.fetchone()
    
    count = int(row.cnt) if row else 0
    cutoff = row.cutoff_day if row else (date.today() - timedelta(days=retention_days))
    
    return count, cutoff


async def delete_old_snapshots(db: AsyncSession, retention_days: int, limit: int = MAX_RECORDS_PER_RUN) -> int:
    """
    Delete old storage snapshots.
    
    Uses deterministic ORDER BY day for consistent batches.
    Never deletes current day.
    
    Returns:
        Number of rows deleted
    """
    # Subquery with ORDER BY for deterministic batches
    q = text("""
        DELETE FROM kpis.storage_daily_snapshots
        WHERE day IN (
            SELECT day
            FROM kpis.storage_daily_snapshots
            WHERE day < CURRENT_DATE - make_interval(days => :retention_days)
            ORDER BY day
            LIMIT :limit
        )
    """)
    
    res = await db.execute(q, {"retention_days": retention_days, "limit": limit})
    return res.rowcount or 0


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTER
# ═══════════════════════════════════════════════════════════════════════════════

router = APIRouter(
    prefix="/_internal/admin/projects-files/operational/cleanup",
    tags=["admin-cleanup"],
    dependencies=[Depends(require_admin_strict)],
)


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS - Ghost Files
# ═══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/ghost-files/dry-run",
    response_model=DryRunResponse,
)
async def ghost_files_dry_run(
    db: AsyncSession = Depends(get_db),
):
    """
    Dry-run: Count ghost files eligible for cleanup.
    
    Returns count of records that would be deleted without making changes.
    Required before actual cleanup execution.
    """
    try:
        # Count eligible records
        eligible_count = await count_ghost_files(db)
        
        # Check rate limit (fail-closed)
        can_execute, next_allowed = await check_rate_limit(db, "admin_cleanup_ghost_files")
        
        # Calculate estimated batches
        estimated_batches = (eligible_count + MAX_RECORDS_PER_RUN - 1) // MAX_RECORDS_PER_RUN if eligible_count > 0 else 0
        
        logger.info(
            f"[cleanup_dry_run] ghost_files eligible={eligible_count} "
            f"batches={estimated_batches} can_execute={can_execute}"
        )
        
        return DryRunResponse(
            eligible_count=eligible_count,
            estimated_batches=max(1, estimated_batches) if eligible_count > 0 else 0,
            max_per_run=MAX_RECORDS_PER_RUN,
            rate_limit_minutes=RATE_LIMIT_MINUTES,
            can_execute=can_execute,
            next_allowed_at=next_allowed.isoformat() + "Z" if next_allowed else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[cleanup_dry_run] Error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error during dry-run: {str(e)}",
        )


@router.post(
    "/ghost-files",
    response_model=CleanupResponse,
)
async def cleanup_ghost_files(
    request: CleanupRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Execute ghost files cleanup.
    
    Deletes records from input_files where:
    - input_file_is_active = true
    - storage_exists = false
    
    Requirements:
    - confirm_text must be exactly "CONFIRMAR LIMPIEZA"
    - Rate limit: 1 execution per 10 minutes
    - Max 5000 records per execution
    
    All executions are logged to kpis.job_executions for audit.
    """
    import time
    start_time = time.time()
    
    # ─────────────────────────────────────────────────────────────
    # Validation: Confirm text
    # ─────────────────────────────────────────────────────────────
    if request.confirm_text != REQUIRED_CONFIRM_TEXT_GHOST:
        raise HTTPException(
            status_code=400,
            detail=f"Texto de confirmación incorrecto. Debe ser exactamente: {REQUIRED_CONFIRM_TEXT_GHOST}",
        )
    
    # ─────────────────────────────────────────────────────────────
    # Validation: Rate limit (fail-closed)
    # ─────────────────────────────────────────────────────────────
    can_execute, next_allowed = await check_rate_limit(db, "admin_cleanup_ghost_files")
    
    if not can_execute:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit activo. Próxima ejecución permitida: {next_allowed.isoformat() if next_allowed else 'desconocido'}",
        )
    
    # ─────────────────────────────────────────────────────────────
    # Validation: SSOT columns exist
    # ─────────────────────────────────────────────────────────────
    try:
        q_check = text("""
            SELECT 
                COUNT(*) FILTER (WHERE column_name = 'input_file_is_active') AS has_active,
                COUNT(*) FILTER (WHERE column_name = 'storage_exists') AS has_storage
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'input_files'
        """)
        res_check = await db.execute(q_check)
        row_check = res_check.fetchone()
        
        if not row_check or row_check.has_active == 0 or row_check.has_storage == 0:
            raise HTTPException(
                status_code=500,
                detail="SSOT columns missing: input_file_is_active or storage_exists not found in input_files",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[cleanup] SSOT validation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error validating SSOT: {str(e)}",
        )
    
    # ─────────────────────────────────────────────────────────────
    # Count before deletion (for audit)
    # ─────────────────────────────────────────────────────────────
    eligible_before = await count_ghost_files(db)
    
    if eligible_before == 0:
        raise HTTPException(
            status_code=400,
            detail="No hay archivos fantasma elegibles para limpiar",
        )
    
    # ─────────────────────────────────────────────────────────────
    # Execute cleanup with job tracking
    # ─────────────────────────────────────────────────────────────
    async with JobExecutionTracker(
        db,
        job_id="admin_cleanup_ghost_files",
        job_type="manual_admin",
        module="files",
    ) as tracker:
        try:
            deleted_count = await delete_ghost_files(db, MAX_RECORDS_PER_RUN)
            
            # Commit the transaction
            await db.commit()
            
            # Count remaining
            remaining = await count_ghost_files(db)
            
            # Set result for tracker
            tracker.set_result({
                "deleted_count": deleted_count,
                "eligible_before": eligible_before,
                "remaining_after": remaining,
            })
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.info(
                f"[cleanup] ghost_files deleted={deleted_count} "
                f"remaining={remaining} duration_ms={duration_ms}"
            )
            
            # Build message
            if remaining > 0:
                message = f"Limpieza completada. Eliminados {deleted_count} registros. Quedan {remaining} pendientes (ejecutar de nuevo)."
            else:
                message = f"Limpieza completada. Eliminados {deleted_count} registros. No quedan pendientes."
            
            return CleanupResponse(
                deleted_count=deleted_count,
                execution_id=str(tracker.execution_id) if tracker.execution_id else "not-tracked",
                duration_ms=duration_ms,
                remaining=remaining,
                message=message,
            )
        
        except Exception as e:
            # Rollback on any error
            await db.rollback()
            tracker.set_error(str(e))
            logger.exception(f"[cleanup] Error during execution: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error durante la limpieza: {str(e)}",
            )


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS - Storage Snapshots
# ═══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/storage-snapshots/dry-run",
    response_model=SnapshotsDryRunResponse,
)
async def storage_snapshots_dry_run(
    retention_days: int = Query(DEFAULT_RETENTION_DAYS, ge=MIN_RETENTION_DAYS, le=MAX_RETENTION_DAYS),
    db: AsyncSession = Depends(get_db),
):
    """
    Dry-run: Count storage snapshots older than retention period.
    
    Args:
        retention_days: Days to retain (30-365, default 180)
    
    Returns count of rows that would be deleted without making changes.
    Required before actual cleanup execution.
    
    IMPORTANT: This only deletes metadata rows, NOT actual storage files.
    """
    try:
        # Verify table exists (fail-closed)
        await verify_snapshots_table_exists(db)
        
        # Count eligible records
        eligible_count, cutoff_day = await count_old_snapshots(db, retention_days)
        
        # Check rate limit (fail-closed)
        can_execute, next_allowed = await check_rate_limit(db, "admin_cleanup_storage_snapshots")
        
        # Calculate estimated batches
        estimated_batches = (eligible_count + MAX_RECORDS_PER_RUN - 1) // MAX_RECORDS_PER_RUN if eligible_count > 0 else 0
        
        logger.info(
            f"[cleanup_dry_run] storage_snapshots eligible={eligible_count} "
            f"cutoff={cutoff_day} retention={retention_days}d can_execute={can_execute}"
        )
        
        return SnapshotsDryRunResponse(
            eligible_count=eligible_count,
            cutoff_day=cutoff_day.isoformat(),
            estimated_batches=max(1, estimated_batches) if eligible_count > 0 else 0,
            max_per_run=MAX_RECORDS_PER_RUN,
            rate_limit_minutes=RATE_LIMIT_MINUTES,
            can_execute=can_execute,
            next_allowed_at=next_allowed.isoformat() + "Z" if next_allowed else None,
            retention_days=retention_days,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[cleanup_dry_run] storage_snapshots Error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error during dry-run: {str(e)}",
        )


@router.post(
    "/storage-snapshots",
    response_model=SnapshotsCleanupResponse,
)
async def cleanup_storage_snapshots(
    request: SnapshotsCleanupRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Execute storage snapshots cleanup.
    
    Deletes rows from kpis.storage_daily_snapshots where:
    - day < CURRENT_DATE - retention_days
    
    Requirements:
    - confirm_text must be exactly "CONFIRMAR LIMPIEZA SNAPSHOTS"
    - retention_days must be 30-365 (default 180)
    - Rate limit: 1 execution per 10 minutes
    - Max 5000 rows per execution
    
    IMPORTANT: This only deletes metadata rows, NOT actual storage files.
    All executions are logged to kpis.job_executions for audit.
    """
    import time
    start_time = time.time()
    
    # ─────────────────────────────────────────────────────────────
    # Validation: Confirm text
    # ─────────────────────────────────────────────────────────────
    if request.confirm_text != REQUIRED_CONFIRM_TEXT_SNAPSHOTS:
        raise HTTPException(
            status_code=400,
            detail=f"Texto de confirmación incorrecto. Debe ser exactamente: {REQUIRED_CONFIRM_TEXT_SNAPSHOTS}",
        )
    
    # ─────────────────────────────────────────────────────────────
    # Validation: SSOT table exists (fail-closed)
    # ─────────────────────────────────────────────────────────────
    await verify_snapshots_table_exists(db)
    
    # ─────────────────────────────────────────────────────────────
    # Validation: Rate limit (fail-closed)
    # ─────────────────────────────────────────────────────────────
    can_execute, next_allowed = await check_rate_limit(db, "admin_cleanup_storage_snapshots")
    
    if not can_execute:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit activo. Próxima ejecución permitida: {next_allowed.isoformat() if next_allowed else 'desconocido'}",
        )
    
    # ─────────────────────────────────────────────────────────────
    # Count before deletion (for audit)
    # ─────────────────────────────────────────────────────────────
    eligible_before, cutoff_day = await count_old_snapshots(db, request.retention_days)
    
    if eligible_before == 0:
        raise HTTPException(
            status_code=400,
            detail=f"No hay snapshots antiguos para limpiar (retención: {request.retention_days} días)",
        )
    
    # ─────────────────────────────────────────────────────────────
    # Execute cleanup with job tracking
    # ─────────────────────────────────────────────────────────────
    async with JobExecutionTracker(
        db,
        job_id="admin_cleanup_storage_snapshots",
        job_type="manual_admin",
        module="storage",
    ) as tracker:
        try:
            deleted_count = await delete_old_snapshots(db, request.retention_days, MAX_RECORDS_PER_RUN)
            
            # Commit the transaction
            await db.commit()
            
            # Count remaining
            remaining, _ = await count_old_snapshots(db, request.retention_days)
            
            # Set result for tracker
            tracker.set_result({
                "deleted_count": deleted_count,
                "eligible_before": eligible_before,
                "remaining_after": remaining,
                "cutoff_day": cutoff_day.isoformat(),
                "retention_days": request.retention_days,
            })
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.info(
                f"[cleanup] storage_snapshots deleted={deleted_count} "
                f"remaining={remaining} cutoff={cutoff_day} duration_ms={duration_ms}"
            )
            
            # Build message
            if remaining > 0:
                message = f"Limpieza completada. Eliminados {deleted_count} snapshots anteriores a {cutoff_day}. Quedan {remaining} pendientes."
            else:
                message = f"Limpieza completada. Eliminados {deleted_count} snapshots anteriores a {cutoff_day}. No quedan pendientes."
            
            return SnapshotsCleanupResponse(
                deleted_count=deleted_count,
                remaining=remaining,
                cutoff_day=cutoff_day.isoformat(),
                execution_id=str(tracker.execution_id) if tracker.execution_id else "not-tracked",
                duration_ms=duration_ms,
                message=message,
            )
        
        except Exception as e:
            # Rollback on any error
            await db.rollback()
            tracker.set_error(str(e))
            logger.exception(f"[cleanup] storage_snapshots Error during execution: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error durante la limpieza: {str(e)}",
            )


# Fin del archivo
