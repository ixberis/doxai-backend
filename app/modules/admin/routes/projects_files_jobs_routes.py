# -*- coding: utf-8 -*-
"""
backend/app/modules/admin/routes/projects_files_jobs_routes.py

Admin endpoints for Jobs & Errors metrics (OPERACIÓN / Jobs).

Exposes read-only JSON endpoints for the admin dashboard:
- GET /_internal/admin/projects-files/operational/jobs - Job executions + errors
- POST /_internal/admin/jobs/prune - Cleanup old job executions (cron external)

Author: DoxAI
Created: 2026-01-23
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.modules.auth.dependencies import require_admin_strict
from app.shared.internal_auth import require_internal_service_token


logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class JobExecution(BaseModel):
    """Single job execution record."""
    execution_id: str
    job_id: str
    job_type: str
    module: str
    started_at: str
    finished_at: Optional[str] = None
    duration_ms: Optional[int] = None
    status: str
    result_summary: Optional[dict] = None
    error_message: Optional[str] = None


class JobKPIs(BaseModel):
    """KPIs for jobs dashboard."""
    jobs_failed_24h: int = Field(0, description="Failed jobs in last 24h")
    jobs_success_24h: int = Field(0, description="Successful jobs in last 24h")
    jobs_running: int = Field(0, description="Currently running jobs")
    total_executions_24h: int = Field(0, description="Total executions in 24h")


class LastJobStatus(BaseModel):
    """Last execution status for a critical job."""
    job_id: str
    last_status: str
    last_run_at: Optional[str] = None
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None


class RecentError(BaseModel):
    """Recent job error."""
    job_id: str
    module: str
    started_at: str
    error_message: str
    execution_id: str


class JobsMetricsResponse(BaseModel):
    """Complete jobs metrics response."""
    kpis: JobKPIs = Field(default_factory=JobKPIs)
    critical_jobs: list[LastJobStatus] = Field(default_factory=list)
    recent_executions: list[JobExecution] = Field(default_factory=list)
    recent_errors: list[RecentError] = Field(default_factory=list)
    generated_at: str
    ssot_validated: bool = True


class PruneResponse(BaseModel):
    """Response from prune operation."""
    success: bool
    deleted_count: int
    cutoff_date: str
    retention_days: int
    pruned_at: str


# ═══════════════════════════════════════════════════════════════════════════════
# SSOT VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

class SSOTMissingError(Exception):
    """Raised when a required SSOT object is missing."""
    pass


async def validate_jobs_ssot(db: AsyncSession) -> bool:
    """
    Validate job_executions table exists.
    
    Returns:
        True if validated
        
    Raises:
        SSOTMissingError if missing
    """
    q = text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'kpis'
              AND table_name = 'job_executions'
        ) AS exists
    """)
    res = await db.execute(q)
    exists = bool(res.scalar())
    
    if not exists:
        raise SSOTMissingError(
            "kpis.job_executions table not found. "
            "Run database/observability/ migrations."
        )
    
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# AGGREGATOR
# ═══════════════════════════════════════════════════════════════════════════════

# Critical jobs to monitor
CRITICAL_JOBS = [
    "capture_storage_snapshot",
    "files_reconcile_storage_ghosts",
]


class JobsMetricsAggregator:
    """Aggregator for jobs metrics from DB."""
    
    def __init__(self, db: AsyncSession, hours: int = 24, limit: int = 100):
        self.db = db
        self.hours = min(hours, 168)  # Cap at 7 days
        self.limit = min(limit, 500)  # Cap at 500
    
    async def get_metrics(self) -> JobsMetricsResponse:
        """Get complete jobs metrics."""
        await validate_jobs_ssot(self.db)
        
        kpis = await self._get_kpis()
        critical_jobs = await self._get_critical_jobs_status()
        recent_executions = await self._get_recent_executions()
        recent_errors = await self._get_recent_errors()
        
        return JobsMetricsResponse(
            kpis=kpis,
            critical_jobs=critical_jobs,
            recent_executions=recent_executions,
            recent_errors=recent_errors,
            generated_at=datetime.utcnow().isoformat() + "Z",
            ssot_validated=True,
        )
    
    async def _get_kpis(self) -> JobKPIs:
        """Get KPI counts."""
        q = text("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'failed' AND started_at > now() - make_interval(hours => :hours)) AS failed_24h,
                COUNT(*) FILTER (WHERE status = 'success' AND started_at > now() - make_interval(hours => :hours)) AS success_24h,
                COUNT(*) FILTER (WHERE status = 'running') AS running,
                COUNT(*) FILTER (WHERE started_at > now() - make_interval(hours => :hours)) AS total_24h
            FROM kpis.job_executions
        """)
        res = await self.db.execute(q, {"hours": self.hours})
        row = res.fetchone()
        
        if not row:
            return JobKPIs()
        
        return JobKPIs(
            jobs_failed_24h=int(row.failed_24h or 0),
            jobs_success_24h=int(row.success_24h or 0),
            jobs_running=int(row.running or 0),
            total_executions_24h=int(row.total_24h or 0),
        )
    
    async def _get_critical_jobs_status(self) -> list[LastJobStatus]:
        """Get last execution status for critical jobs."""
        results = []
        
        for job_id in CRITICAL_JOBS:
            q = text("""
                SELECT 
                    job_id,
                    status,
                    started_at,
                    duration_ms,
                    error_message
                FROM kpis.job_executions
                WHERE job_id = :job_id
                ORDER BY started_at DESC
                LIMIT 1
            """)
            res = await self.db.execute(q, {"job_id": job_id})
            row = res.fetchone()
            
            if row:
                results.append(LastJobStatus(
                    job_id=row.job_id,
                    last_status=row.status,
                    last_run_at=row.started_at.isoformat() if row.started_at else None,
                    duration_ms=int(row.duration_ms) if row.duration_ms else None,
                    error_message=row.error_message,
                ))
            else:
                # Job never ran
                results.append(LastJobStatus(
                    job_id=job_id,
                    last_status="never_ran",
                    last_run_at=None,
                    duration_ms=None,
                    error_message=None,
                ))
        
        return results
    
    async def _get_recent_executions(self) -> list[JobExecution]:
        """Get recent job executions."""
        q = text("""
            SELECT 
                execution_id,
                job_id,
                job_type,
                module,
                started_at,
                finished_at,
                duration_ms,
                status,
                result_summary,
                error_message
            FROM kpis.job_executions
            WHERE started_at > now() - make_interval(hours => :hours)
            ORDER BY started_at DESC
            LIMIT :limit
        """)
        res = await self.db.execute(q, {"hours": self.hours, "limit": self.limit})
        rows = res.fetchall()
        
        return [
            JobExecution(
                execution_id=str(row.execution_id),
                job_id=row.job_id,
                job_type=row.job_type,
                module=row.module,
                started_at=row.started_at.isoformat() if row.started_at else "",
                finished_at=row.finished_at.isoformat() if row.finished_at else None,
                duration_ms=int(row.duration_ms) if row.duration_ms else None,
                status=row.status,
                result_summary=dict(row.result_summary) if row.result_summary else None,
                error_message=row.error_message,
            )
            for row in rows
        ]
    
    async def _get_recent_errors(self) -> list[RecentError]:
        """Get recent job errors."""
        q = text("""
            SELECT 
                execution_id,
                job_id,
                module,
                started_at,
                error_message
            FROM kpis.job_executions
            WHERE status = 'failed'
              AND started_at > now() - make_interval(hours => :hours)
              AND error_message IS NOT NULL
            ORDER BY started_at DESC
            LIMIT 20
        """)
        res = await self.db.execute(q, {"hours": self.hours})
        rows = res.fetchall()
        
        return [
            RecentError(
                execution_id=str(row.execution_id),
                job_id=row.job_id,
                module=row.module,
                started_at=row.started_at.isoformat() if row.started_at else "",
                error_message=row.error_message or "",
            )
            for row in rows
        ]


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTER
# ═══════════════════════════════════════════════════════════════════════════════

router = APIRouter(
    prefix="/_internal/admin",
    tags=["admin-jobs"],
    dependencies=[Depends(require_admin_strict)],
)


@router.get(
    "/projects-files/operational/jobs",
    response_model=JobsMetricsResponse,
)
async def get_jobs_metrics(
    hours: int = Query(24, ge=1, le=168, description="Hours of history to fetch"),
    limit: int = Query(100, ge=1, le=500, description="Max executions to return"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get Jobs & Errors metrics for admin dashboard.
    
    Returns:
    - kpis: Counts of failed/success/running jobs
    - critical_jobs: Last status of critical jobs
    - recent_executions: Recent job executions
    - recent_errors: Recent job failures with error messages
    """
    aggregator = JobsMetricsAggregator(db, hours=hours, limit=limit)
    
    try:
        metrics = await aggregator.get_metrics()
        logger.info(
            f"[jobs_metrics] "
            f"failed_24h={metrics.kpis.jobs_failed_24h} "
            f"success_24h={metrics.kpis.jobs_success_24h} "
            f"running={metrics.kpis.jobs_running}"
        )
        return metrics
    except SSOTMissingError as e:
        logger.error(f"[jobs_metrics] SSOT missing: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception(f"[jobs_metrics] Error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving jobs metrics",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PRUNE ENDPOINT (for external cron)
# ═══════════════════════════════════════════════════════════════════════════════

prune_router = APIRouter(
    prefix="/_internal/cron/jobs",
    tags=["cron-jobs"],
)


@prune_router.post(
    "/prune",
    response_model=PruneResponse,
    dependencies=[Depends(require_internal_service_token)],
)
async def prune_job_executions(
    retention_days: int = Query(90, ge=7, le=365, description="Days to retain"),
    db: AsyncSession = Depends(get_db),
):
    """
    Prune old job execution records.
    
    Protected by internal service token (not JWT).
    Called by external cron (Railway/GitHub Actions) daily.
    
    Recommended schedule: Daily at 03:00 UTC
    RRULE: FREQ=DAILY;BYHOUR=3;BYMINUTE=0
    
    Calls kpis.fn_job_executions_prune(retention_days).
    """
    try:
        # Check if function exists
        q_check = text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_proc p
                JOIN pg_namespace n ON p.pronamespace = n.oid
                WHERE n.nspname = 'kpis'
                  AND p.proname = 'fn_job_executions_prune'
            ) AS exists
        """)
        res_check = await db.execute(q_check)
        if not res_check.scalar():
            raise HTTPException(
                status_code=500,
                detail="kpis.fn_job_executions_prune not installed. Run migrations."
            )
        
        # Call prune function
        q = text("SELECT kpis.fn_job_executions_prune(:retention_days) AS result")
        res = await db.execute(q, {"retention_days": retention_days})
        result = res.scalar()
        
        await db.commit()
        
        logger.info(f"[prune_jobs] Success: {result}")
        
        return PruneResponse(
            success=result.get("success", False) if result else False,
            deleted_count=result.get("deleted_count", 0) if result else 0,
            cutoff_date=str(result.get("cutoff_date", "")) if result else "",
            retention_days=retention_days,
            pruned_at=datetime.utcnow().isoformat() + "Z",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[prune_jobs] Error: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error pruning job executions: {str(e)}",
        )


# Fin del archivo
