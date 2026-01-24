# -*- coding: utf-8 -*-
"""
backend/app/shared/observability/job_execution_tracker.py

Helper para instrumentar ejecuciones de jobs en kpis.job_executions.

Uso:
    async with JobExecutionTracker(db, "my_job", "cron_external", "files") as tracker:
        # ... ejecutar lógica del job ...
        tracker.set_result({"items_processed": 100})

O sin context manager:
    tracker = JobExecutionTracker(db, "my_job", "cron_external", "files")
    await tracker.start()
    try:
        # ... ejecutar lógica del job ...
        await tracker.finish_success({"items_processed": 100})
    except Exception as e:
        await tracker.finish_failed(str(e))

Author: DoxAI
Created: 2026-01-23
"""
import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)


class JobExecutionTracker:
    """
    Context manager and helper for tracking job executions.
    
    Registers start/finish in kpis.job_executions table.
    Handles errors gracefully (logs but doesn't fail job).
    """
    
    def __init__(
        self,
        db: AsyncSession,
        job_id: str,
        job_type: str,
        module: str,
    ):
        """
        Initialize tracker.
        
        Args:
            db: Database session
            job_id: Logical job name (e.g., "files_reconcile_storage_ghosts")
            job_type: One of "scheduler", "cron_external", "pg_cron"
            module: One of "files", "storage", "projects", "auth", "rag"
        """
        self.db = db
        self.job_id = job_id
        self.job_type = job_type
        self.module = module
        self.execution_id: Optional[UUID] = None
        self._result: Optional[dict] = None
        self._error: Optional[str] = None
        self._table_exists: Optional[bool] = None
    
    async def _check_table_exists(self) -> bool:
        """Check if kpis.job_executions table exists."""
        if self._table_exists is not None:
            return self._table_exists
        
        try:
            q = text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'kpis'
                      AND table_name = 'job_executions'
                ) AS exists
            """)
            res = await self.db.execute(q)
            self._table_exists = bool(res.scalar())
        except Exception:
            self._table_exists = False
        
        return self._table_exists
    
    async def start(self) -> Optional[UUID]:
        """
        Register job execution start.
        
        Returns:
            execution_id if registered, None if table not available
        """
        if not await self._check_table_exists():
            logger.debug(f"[job_tracker] Table not available, skipping start for {self.job_id}")
            return None
        
        try:
            # SQLAlchemy async + asyncpg: use named binds with dict params
            q = text("""
                SELECT kpis.fn_job_execution_start(:job_id, :job_type, :module) AS execution_id
            """)
            res = await self.db.execute(q, {
                "job_id": self.job_id,
                "job_type": self.job_type,
                "module": self.module,
            })
            self.execution_id = res.scalar()
            
            logger.info(
                f"[job_tracker] Started {self.job_id} (execution_id={self.execution_id})"
            )
            return self.execution_id
        except Exception as e:
            logger.warning(f"[job_tracker] Failed to start {self.job_id}: {e}")
            return None
    
    async def finish_success(self, result_summary: Optional[dict] = None) -> None:
        """
        Register successful job completion.
        
        Args:
            result_summary: Optional dict with job results (kept small)
        """
        await self._finish("success", result_summary, None)
    
    async def finish_failed(self, error_message: str, result_summary: Optional[dict] = None) -> None:
        """
        Register failed job completion.
        
        Args:
            error_message: Error message (truncated to 500 chars)
            result_summary: Optional dict with partial results
        """
        await self._finish("failed", result_summary, error_message[:500])
    
    async def _finish(
        self,
        status: str,
        result_summary: Optional[dict],
        error_message: Optional[str],
    ) -> None:
        """Internal finish helper."""
        if not self.execution_id:
            logger.debug(f"[job_tracker] No execution_id, skipping finish for {self.job_id}")
            return
        
        try:
            import json
            
            # Validate result_summary is dict or None
            if result_summary is not None and not isinstance(result_summary, dict):
                logger.warning(
                    f"[job_tracker] result_summary is not dict, forcing None: {type(result_summary)}"
                )
                result_summary = None
            
            result_json = json.dumps(result_summary) if result_summary else None
            
            # SQLAlchemy async + asyncpg: use named binds with dict params
            # Use CAST(...AS jsonb) instead of ::jsonb to avoid parser confusion
            q = text("""
                SELECT kpis.fn_job_execution_finish(
                    :execution_id,
                    :status,
                    CAST(:result_summary AS jsonb),
                    :error_message
                ) AS result
            """)
            await self.db.execute(q, {
                "execution_id": self.execution_id,
                "status": status,
                "result_summary": result_json,
                "error_message": error_message,
            })
            
            logger.info(
                f"[job_tracker] Finished {self.job_id} ({status}) "
                f"execution_id={self.execution_id}"
            )
        except Exception as e:
            logger.warning(f"[job_tracker] Failed to finish {self.job_id}: {e}")
    
    def set_result(self, result: dict) -> None:
        """Set result for context manager use."""
        self._result = result
    
    def set_error(self, error: str) -> None:
        """Set error for context manager use."""
        self._error = error[:500]
    
    async def __aenter__(self) -> "JobExecutionTracker":
        """Context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        if exc_type is not None:
            # Exception occurred
            error_msg = str(exc_val)[:500] if exc_val else "Unknown error"
            await self.finish_failed(error_msg, self._result)
        elif self._error:
            # Error set manually
            await self.finish_failed(self._error, self._result)
        else:
            # Success
            await self.finish_success(self._result)


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

async def track_job_execution(
    db: AsyncSession,
    job_id: str,
    job_type: str,
    module: str,
) -> JobExecutionTracker:
    """
    Create and start a job execution tracker.
    
    Usage:
        tracker = await track_job_execution(db, "my_job", "cron_external", "files")
        try:
            # ... do work ...
            await tracker.finish_success({"count": 10})
        except Exception as e:
            await tracker.finish_failed(str(e))
    """
    tracker = JobExecutionTracker(db, job_id, job_type, module)
    await tracker.start()
    return tracker


__all__ = [
    "JobExecutionTracker",
    "track_job_execution",
]
