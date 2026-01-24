# -*- coding: utf-8 -*-
"""
backend/app/modules/admin/routes/projects_files_health_routes.py

Admin endpoints for Projects/Files Health metrics (OPERACIÓN > Archivos > Salud).

Exposes read-only JSON endpoints:
- GET /_internal/admin/projects-files/operational/files-health

Provides visibility into:
- File errors (24h) with breakdown by error_code
- Files in ERROR state (pipeline)
- Stuck files (processing > 30 min)
- Recent file events (from product_file_activity)
- Pipeline state distribution

SSOT Rules:
- Canonical timestamp: event_at (NOT created_at)
- Error breakdown: details->>'error_code' (string, not HTTP status)
- No join to auth.users (use truncated auth_user_id)
- Stuck files from input_files with input_file_status='processing'
- Fail-fast if SSOT columns missing

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


logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class ErrorBreakdown(BaseModel):
    """Breakdown of errors by error_code."""
    error_code: str = Field(..., description="Error code from details JSONB")
    count: int = Field(..., description="Number of occurrences")


class FilesErrorsMetrics(BaseModel):
    """File errors in the last 24h."""
    total: int = Field(0, description="Total failed events in period")
    breakdown: list[ErrorBreakdown] = Field(
        default_factory=list,
        description="Breakdown by error_code"
    )


class FilesErrorStateMetrics(BaseModel):
    """Files currently in ERROR/failed state."""
    count: int = Field(0, description="Files with input_file_status='failed'")
    status: str = Field("healthy", description="healthy | warning | critical")


class StuckFilesMetrics(BaseModel):
    """Files stuck in processing state."""
    count: int = Field(0, description="Files processing > threshold")
    threshold_minutes: int = Field(30, description="Threshold in minutes")
    status: str = Field("healthy", description="healthy | warning | critical")


class PipelineStateCount(BaseModel):
    """Count of files by pipeline state."""
    status: str = Field(..., description="Pipeline status")
    count: int = Field(..., description="Number of files")


class FileEvent(BaseModel):
    """Single file event for the events table."""
    timestamp: str = Field(..., description="ISO timestamp (event_at)")
    project_id: str = Field(..., description="Project UUID")
    user_id_short: str = Field(..., description="First 8 chars of auth_user_id")
    event_type: str = Field(..., description="Event type enum value")
    file_name: str = Field(..., description="File name with fallback")
    error_code: Optional[str] = Field(None, description="Error code if applicable")
    file_type: Optional[str] = Field(None, description="input | product")


class ErrorsByHour(BaseModel):
    """Errors grouped by hour for charting."""
    hour: str = Field(..., description="ISO timestamp of hour")
    error_code: str = Field(..., description="Error code")
    count: int = Field(..., description="Number of errors")


class FilesHealthSummary(BaseModel):
    """
    Files Health summary for admin dashboard.
    
    All metrics are DB-sourced (no Prometheus).
    """
    # ─────────────────────────────────────────────────────────────
    # KPI Cards
    # ─────────────────────────────────────────────────────────────
    errors_24h: FilesErrorsMetrics = Field(
        default_factory=FilesErrorsMetrics,
        description="File errors in last 24h"
    )
    error_state: FilesErrorStateMetrics = Field(
        default_factory=FilesErrorStateMetrics,
        description="Files in ERROR state"
    )
    stuck_files: StuckFilesMetrics = Field(
        default_factory=StuckFilesMetrics,
        description="Files stuck in processing"
    )
    
    # ─────────────────────────────────────────────────────────────
    # Table: Recent Events
    # ─────────────────────────────────────────────────────────────
    recent_events: list[FileEvent] = Field(
        default_factory=list,
        description="Last 100 file events"
    )
    
    # ─────────────────────────────────────────────────────────────
    # Charts
    # ─────────────────────────────────────────────────────────────
    errors_by_hour: list[ErrorsByHour] = Field(
        default_factory=list,
        description="Errors grouped by hour for charting"
    )
    pipeline_states: list[PipelineStateCount] = Field(
        default_factory=list,
        description="Current pipeline state distribution"
    )
    
    # ─────────────────────────────────────────────────────────────
    # Meta
    # ─────────────────────────────────────────────────────────────
    period_hours: int = Field(24, description="Period for time-based metrics")
    generated_at: str = Field(..., description="ISO timestamp of generation")


# ═══════════════════════════════════════════════════════════════════════════════
# AGGREGATOR
# ═══════════════════════════════════════════════════════════════════════════════

class SSOTMissingError(Exception):
    """Raised when a required SSOT object is missing."""
    pass


class FilesHealthAggregator:
    """
    Aggregator for Files Health metrics.
    
    SSOT Rules:
    - Canonical timestamp: event_at (NOT created_at)
    - Error breakdown: details->>'error_code' (string)
    - No join to auth.users
    - Stuck files from input_files
    """
    
    def __init__(self, db: AsyncSession, period_hours: int = 24):
        self.db = db
        self.period_hours = period_hours
    
    async def get_summary(self) -> FilesHealthSummary:
        """Get files health summary."""
        # Validate SSOT requirements
        await self._validate_ssot()
        
        # Gather all metrics
        errors_24h = await self._get_errors_24h()
        error_state = await self._get_error_state_files()
        stuck_files = await self._get_stuck_files()
        recent_events = await self._get_recent_events()
        errors_by_hour = await self._get_errors_by_hour()
        pipeline_states = await self._get_pipeline_states()
        
        return FilesHealthSummary(
            errors_24h=errors_24h,
            error_state=error_state,
            stuck_files=stuck_files,
            recent_events=recent_events,
            errors_by_hour=errors_by_hour,
            pipeline_states=pipeline_states,
            period_hours=self.period_hours,
            generated_at=datetime.utcnow().isoformat() + "Z",
        )
    
    async def _validate_ssot(self) -> None:
        """Validate required SSOT columns exist. Fail-fast if missing."""
        # Define all required columns for validation
        required_columns = [
            # product_file_activity columns
            ("product_file_activity", "event_at", "05_product_file_activity.sql"),
            ("product_file_activity", "details", "05_product_file_activity.sql"),
            ("product_file_activity", "snapshot_name", "05_product_file_activity.sql"),
            # input_files columns
            ("input_files", "input_file_status", "01_input_files.sql"),
            ("input_files", "input_file_is_active", "01_input_files.sql"),
            ("input_files", "updated_at", "01_input_files.sql"),
        ]
        
        for table_name, column_name, script_name in required_columns:
            q_check = text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                      AND column_name = :column_name
                ) AS exists
            """)
            res = await self.db.execute(q_check, {"table_name": table_name, "column_name": column_name})
            if not res.scalar():
                raise SSOTMissingError(
                    f"{table_name}.{column_name} column not installed. "
                    f"Run database/files/02_tables/{script_name}"
                )
    
    async def _get_errors_24h(self) -> FilesErrorsMetrics:
        """Get file errors in the last 24h with breakdown by error_code."""
        q = text("""
            SELECT 
                COALESCE(details->>'error_code', 'unknown') AS error_code,
                COUNT(*) AS count
            FROM product_file_activity
            WHERE event_type = 'failed'
              AND event_at > now() - make_interval(hours => :period_hours)
            GROUP BY error_code
            ORDER BY count DESC
        """)
        res = await self.db.execute(q, {"period_hours": self.period_hours})
        rows = res.fetchall()
        
        breakdown = [
            ErrorBreakdown(error_code=str(r.error_code), count=int(r.count))
            for r in rows
        ]
        total = sum(b.count for b in breakdown)
        
        return FilesErrorsMetrics(total=total, breakdown=breakdown)
    
    async def _get_error_state_files(self) -> FilesErrorStateMetrics:
        """Get count of files currently in failed/error state."""
        q = text("""
            SELECT COUNT(*) AS count
            FROM input_files
            WHERE input_file_status = 'failed'
              AND input_file_is_active = true
        """)
        res = await self.db.execute(q)
        count = int(res.scalar() or 0)
        
        # Determine status
        if count == 0:
            status = "healthy"
        elif count < 50:
            status = "warning"
        else:
            status = "critical"
        
        return FilesErrorStateMetrics(count=count, status=status)
    
    async def _get_stuck_files(self, threshold_minutes: int = 30) -> StuckFilesMetrics:
        """Get count of files stuck in processing state."""
        q = text("""
            SELECT COUNT(*) AS count
            FROM input_files
            WHERE input_file_status = 'processing'
              AND input_file_is_active = true
              AND updated_at < now() - make_interval(mins => :threshold_minutes)
        """)
        res = await self.db.execute(q, {"threshold_minutes": threshold_minutes})
        count = int(res.scalar() or 0)
        
        # Determine status
        if count == 0:
            status = "healthy"
        elif count < 10:
            status = "warning"
        else:
            status = "critical"
        
        return StuckFilesMetrics(
            count=count,
            threshold_minutes=threshold_minutes,
            status=status
        )
    
    async def _get_recent_events(self, limit: int = 100) -> list[FileEvent]:
        """Get recent file events from product_file_activity."""
        q = text("""
            SELECT 
                pfa.event_at AS timestamp,
                pfa.project_id::text AS project_id,
                LEFT(pfa.auth_user_id::text, 8) AS user_id_short,
                pfa.event_type::text AS event_type,
                COALESCE(
                    pfa.snapshot_name, 
                    pfa.details->>'file_name', 
                    '—'
                ) AS file_name,
                pfa.details->>'error_code' AS error_code,
                pfa.details->>'file_type' AS file_type
            FROM product_file_activity pfa
            WHERE pfa.event_at > now() - make_interval(hours => :period_hours)
            ORDER BY pfa.event_at DESC
            LIMIT :limit
        """)
        res = await self.db.execute(q, {"period_hours": self.period_hours, "limit": limit})
        rows = res.fetchall()
        
        return [
            FileEvent(
                timestamp=r.timestamp.isoformat() if r.timestamp else "",
                project_id=str(r.project_id),
                user_id_short=str(r.user_id_short or ""),
                event_type=str(r.event_type),
                file_name=str(r.file_name),
                error_code=str(r.error_code) if r.error_code else None,
                file_type=str(r.file_type) if r.file_type else None,
            )
            for r in rows
        ]
    
    async def _get_errors_by_hour(self) -> list[ErrorsByHour]:
        """Get errors grouped by hour for charting."""
        q = text("""
            SELECT 
                date_trunc('hour', event_at) AS hour,
                COALESCE(details->>'error_code', 'unknown') AS error_code,
                COUNT(*) AS count
            FROM product_file_activity
            WHERE event_type = 'failed'
              AND event_at > now() - make_interval(hours => :period_hours)
            GROUP BY hour, error_code
            ORDER BY hour
        """)
        res = await self.db.execute(q, {"period_hours": self.period_hours})
        rows = res.fetchall()
        
        return [
            ErrorsByHour(
                hour=r.hour.isoformat() if r.hour else "",
                error_code=str(r.error_code),
                count=int(r.count)
            )
            for r in rows
        ]
    
    async def _get_pipeline_states(self) -> list[PipelineStateCount]:
        """Get current pipeline state distribution."""
        q = text("""
            SELECT 
                input_file_status::text AS status,
                COUNT(*)::bigint AS count
            FROM input_files
            WHERE input_file_is_active = true
            GROUP BY input_file_status
            ORDER BY count DESC
        """)
        res = await self.db.execute(q)
        rows = res.fetchall()
        
        return [
            PipelineStateCount(status=str(r.status), count=int(r.count))
            for r in rows
        ]


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTER
# ═══════════════════════════════════════════════════════════════════════════════

router = APIRouter(
    prefix="/_internal/admin/projects-files/operational",
    tags=["admin-projects-files-health"],
    dependencies=[Depends(require_admin_strict)],
)


@router.get("/files-health", response_model=FilesHealthSummary)
async def get_files_health_summary(
    period: int = Query(24, ge=1, le=168, description="Period in hours (1-168)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get Files Health summary for admin dashboard.
    
    Returns:
    - errors_24h: Failed events with breakdown by error_code
    - error_state: Files currently in failed state
    - stuck_files: Files processing > 30 min
    - recent_events: Last 100 file events
    - errors_by_hour: For error trend chart
    - pipeline_states: Current state distribution
    
    SSOT Rules:
    - Canonical timestamp: event_at
    - Error breakdown: details->>'error_code'
    - No join to auth.users
    """
    aggregator = FilesHealthAggregator(db, period_hours=period)
    
    try:
        summary = await aggregator.get_summary()
        logger.info(
            f"[files_health] "
            f"errors_24h={summary.errors_24h.total} "
            f"error_state={summary.error_state.count} "
            f"stuck={summary.stuck_files.count} "
            f"events={len(summary.recent_events)}"
        )
        return summary
    except SSOTMissingError as e:
        logger.error(f"[files_health] SSOT missing: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"SSOT missing: {str(e)}",
        )
    except Exception as e:
        logger.exception(f"[files_health] Error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving files health metrics",
        )


# Fin del archivo
