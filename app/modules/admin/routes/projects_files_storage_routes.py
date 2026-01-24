# -*- coding: utf-8 -*-
"""
backend/app/modules/admin/routes/projects_files_storage_routes.py

Admin endpoints for Projects/Files Storage metrics (OPERACIÓN / Storage).

Exposes read-only JSON endpoints for the admin dashboard:
- GET /_internal/admin/projects-files/operational/storage - Storage snapshot + historical series
- POST /_internal/admin/storage/capture-snapshot - Trigger daily snapshot capture (cron external)

Author: DoxAI
Created: 2026-01-23
"""
import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.modules.auth.dependencies import require_admin_strict
from app.shared.internal_auth import require_internal_service_token
from app.shared.observability import JobExecutionTracker


logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class CurrentStorageSnapshot(BaseModel):
    """Current storage metrics from v_kpis_storage_snapshot."""
    # Conteos
    total_objects: int = Field(0, description="Total objects in storage")
    ssot_objects: int = Field(0, description="Objects following SSOT path")
    legacy_objects: int = Field(0, description="Legacy path objects")
    
    # Breakdown por path_kind
    ssot_v2_objects: int = Field(0, description="SSOT v2 objects")
    legacy_input_objects: int = Field(0, description="Legacy input objects")
    legacy_output_objects: int = Field(0, description="Legacy output objects")
    unknown_objects: int = Field(0, description="Unknown path objects")
    
    # Bytes
    total_bytes_db: int = Field(0, description="Total bytes from DB")
    total_size_pretty: str = Field("0 B", description="Human-readable size")
    ssot_v2_bytes: int = Field(0, description="SSOT v2 bytes")
    legacy_input_bytes: int = Field(0, description="Legacy input bytes")
    legacy_output_bytes: int = Field(0, description="Legacy output bytes")
    
    # Cobertura
    unique_users: int = Field(0, description="Unique users with files")
    unique_projects: int = Field(0, description="Unique projects with files")
    
    # Deltas
    input_delta_storage_vs_db: int = Field(0, description="Delta input storage vs DB")
    product_delta_storage_vs_db: int = Field(0, description="Delta product storage vs DB")
    
    # Health
    legacy_status: str = Field("unknown", description="healthy | migrating | needs_attention")
    
    # Timestamp
    snapshot_at: Optional[str] = Field(None, description="Snapshot timestamp")


class HistoricalDataPoint(BaseModel):
    """Single data point for historical charts."""
    day: str = Field(..., description="Date in YYYY-MM-DD format")
    ghost_files_count: int = Field(0, description="Ghost files count")
    total_bytes_db: int = Field(0, description="Total bytes from DB")
    ssot_objects: int = Field(0, description="SSOT objects count")
    legacy_objects: int = Field(0, description="Legacy objects count")


class HistoricalSeries(BaseModel):
    """Historical data series for charts."""
    data_points: list[HistoricalDataPoint] = Field(default_factory=list)
    days_available: int = Field(0, description="Number of days with data")
    first_day: Optional[str] = Field(None, description="Earliest day with data")
    last_day: Optional[str] = Field(None, description="Most recent day with data")


class StorageMetricsResponse(BaseModel):
    """Complete storage metrics response."""
    # Current snapshot
    current: CurrentStorageSnapshot = Field(
        default_factory=CurrentStorageSnapshot,
        description="Current storage snapshot from v_kpis_storage_snapshot"
    )
    
    # Ghost files (live count)
    ghost_files_count: int = Field(0, description="Current ghost files count")
    ghost_files_status: str = Field("unknown", description="healthy | warning | critical")
    
    # Historical series
    history: HistoricalSeries = Field(
        default_factory=HistoricalSeries,
        description="Historical snapshots for charts"
    )
    
    # Meta
    generated_at: str = Field(..., description="ISO timestamp")
    ssot_validated: bool = Field(True, description="All SSOT requirements met")


class CaptureSnapshotResponse(BaseModel):
    """Response from snapshot capture."""
    success: bool = Field(..., description="Whether capture succeeded")
    day: str = Field(..., description="Date captured")
    ghost_files_count: int = Field(0, description="Ghost files count captured")
    total_bytes_db: int = Field(0, description="Total bytes captured")
    message: str = Field("", description="Status message")


# ═══════════════════════════════════════════════════════════════════════════════
# SSOT VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

class SSOTMissingError(Exception):
    """Raised when a required SSOT object is missing."""
    pass


async def validate_storage_ssot(db: AsyncSession) -> dict[str, bool]:
    """
    Validate all required SSOT objects for storage metrics.
    
    Checks:
    - public.v_kpis_storage_snapshot (view OR materialized view)
    - public.input_files.storage_exists (column)
    - kpis.storage_daily_snapshots (table)
    - kpis.fn_capture_storage_snapshot (function)
    
    Returns:
        Dict mapping object name to existence status
        
    Raises:
        SSOTMissingError if critical objects are missing
    """
    checks = {}
    
    # Check v_kpis_storage_snapshot view OR materialized view
    q = text("""
        SELECT EXISTS (
            -- Check regular views
            SELECT 1 FROM information_schema.views
            WHERE table_schema = 'public'
              AND table_name = 'v_kpis_storage_snapshot'
            UNION ALL
            -- Check materialized views
            SELECT 1 FROM pg_matviews
            WHERE schemaname = 'public'
              AND matviewname = 'v_kpis_storage_snapshot'
        ) AS exists
    """)
    res = await db.execute(q)
    checks["v_kpis_storage_snapshot"] = bool(res.scalar())
    
    # Check input_files.storage_exists column
    q = text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'input_files'
              AND column_name = 'storage_exists'
        ) AS exists
    """)
    res = await db.execute(q)
    checks["input_files.storage_exists"] = bool(res.scalar())
    
    # Check kpis.storage_daily_snapshots table
    q = text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'kpis'
              AND table_name = 'storage_daily_snapshots'
        ) AS exists
    """)
    res = await db.execute(q)
    checks["kpis.storage_daily_snapshots"] = bool(res.scalar())
    
    # Check kpis.fn_capture_storage_snapshot function
    q = text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            WHERE n.nspname = 'kpis'
              AND p.proname = 'fn_capture_storage_snapshot'
        ) AS exists
    """)
    res = await db.execute(q)
    checks["kpis.fn_capture_storage_snapshot"] = bool(res.scalar())
    
    # Critical objects (fail-fast if missing)
    critical = ["v_kpis_storage_snapshot", "input_files.storage_exists"]
    missing_critical = [obj for obj in critical if not checks.get(obj)]
    
    if missing_critical:
        raise SSOTMissingError(
            f"Critical SSOT objects missing: {', '.join(missing_critical)}. "
            "Run database/storage/ migrations."
        )
    
    return checks


# ═══════════════════════════════════════════════════════════════════════════════
# AGGREGATOR
# ═══════════════════════════════════════════════════════════════════════════════

class StorageMetricsAggregator:
    """Aggregator for storage metrics from DB."""
    
    def __init__(self, db: AsyncSession, days: int = 30):
        self.db = db
        self.days = min(days, 90)  # Cap at 90 days
    
    async def get_metrics(self) -> StorageMetricsResponse:
        """Get complete storage metrics."""
        # Validate SSOT
        ssot_checks = await validate_storage_ssot(self.db)
        
        # Get current snapshot
        current = await self._get_current_snapshot()
        
        # Get ghost files count
        ghost_count, ghost_status = await self._get_ghost_files()
        
        # Get historical series (if table exists)
        history = HistoricalSeries()
        if ssot_checks.get("kpis.storage_daily_snapshots"):
            history = await self._get_historical_series()
        
        return StorageMetricsResponse(
            current=current,
            ghost_files_count=ghost_count,
            ghost_files_status=ghost_status,
            history=history,
            generated_at=datetime.utcnow().isoformat() + "Z",
            ssot_validated=True,
        )
    
    async def _get_current_snapshot(self) -> CurrentStorageSnapshot:
        """Get current snapshot from v_kpis_storage_snapshot."""
        q = text("""
            SELECT 
                total_objects,
                ssot_objects,
                legacy_objects,
                ssot_v2_objects,
                legacy_input_objects,
                legacy_output_objects,
                unknown_objects,
                total_bytes_db,
                total_size_db_pretty,
                ssot_v2_bytes,
                legacy_input_bytes,
                legacy_output_bytes,
                unique_users,
                unique_projects,
                input_delta_storage_vs_db,
                product_delta_storage_vs_db,
                legacy_status,
                snapshot_at
            FROM public.v_kpis_storage_snapshot
        """)
        res = await self.db.execute(q)
        row = res.fetchone()
        
        if not row:
            return CurrentStorageSnapshot()
        
        return CurrentStorageSnapshot(
            total_objects=int(row.total_objects or 0),
            ssot_objects=int(row.ssot_objects or 0),
            legacy_objects=int(row.legacy_objects or 0),
            ssot_v2_objects=int(row.ssot_v2_objects or 0),
            legacy_input_objects=int(row.legacy_input_objects or 0),
            legacy_output_objects=int(row.legacy_output_objects or 0),
            unknown_objects=int(row.unknown_objects or 0),
            total_bytes_db=int(row.total_bytes_db or 0),
            total_size_pretty=str(row.total_size_db_pretty or "0 B"),
            ssot_v2_bytes=int(row.ssot_v2_bytes or 0),
            legacy_input_bytes=int(row.legacy_input_bytes or 0),
            legacy_output_bytes=int(row.legacy_output_bytes or 0),
            unique_users=int(row.unique_users or 0),
            unique_projects=int(row.unique_projects or 0),
            input_delta_storage_vs_db=int(row.input_delta_storage_vs_db or 0),
            product_delta_storage_vs_db=int(row.product_delta_storage_vs_db or 0),
            legacy_status=str(row.legacy_status or "unknown"),
            snapshot_at=row.snapshot_at.isoformat() if row.snapshot_at else None,
        )
    
    async def _get_ghost_files(self) -> tuple[int, str]:
        """Get current ghost files count and status."""
        q = text("""
            SELECT COUNT(*) AS ghost_count
            FROM public.input_files
            WHERE input_file_is_active = true
              AND storage_exists = false
        """)
        res = await self.db.execute(q)
        count = int(res.scalar() or 0)
        
        # Determine status
        if count == 0:
            status = "healthy"
        elif count < 100:
            status = "warning"
        else:
            status = "critical"
        
        return count, status
    
    async def _get_historical_series(self) -> HistoricalSeries:
        """Get historical snapshots for charts."""
        q = text("""
            SELECT 
                day,
                ghost_files_count,
                total_bytes_db,
                ssot_objects,
                legacy_objects
            FROM kpis.storage_daily_snapshots
            WHERE day >= CURRENT_DATE - make_interval(days => :days)
            ORDER BY day ASC
        """)
        res = await self.db.execute(q, {"days": self.days})
        rows = res.fetchall()
        
        if not rows:
            return HistoricalSeries()
        
        data_points = [
            HistoricalDataPoint(
                day=row.day.isoformat(),
                ghost_files_count=int(row.ghost_files_count or 0),
                total_bytes_db=int(row.total_bytes_db or 0),
                ssot_objects=int(row.ssot_objects or 0),
                legacy_objects=int(row.legacy_objects or 0),
            )
            for row in rows
        ]
        
        return HistoricalSeries(
            data_points=data_points,
            days_available=len(data_points),
            first_day=data_points[0].day if data_points else None,
            last_day=data_points[-1].day if data_points else None,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTER
# ═══════════════════════════════════════════════════════════════════════════════

router = APIRouter(
    prefix="/_internal/admin",
    tags=["admin-storage"],
    dependencies=[Depends(require_admin_strict)],
)


@router.get(
    "/projects-files/operational/storage",
    response_model=StorageMetricsResponse,
)
async def get_storage_metrics(
    days: int = Query(30, ge=1, le=90, description="Days of history to fetch"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get storage metrics for admin dashboard.
    
    Returns:
    - current: Current snapshot from v_kpis_storage_snapshot
    - ghost_files_count: Live count of ghost files
    - history: Historical series for charts (last N days)
    
    SSOT Queries:
    - v_kpis_storage_snapshot (current state)
    - input_files WHERE storage_exists=false (ghost files)
    - kpis.storage_daily_snapshots (historical)
    """
    aggregator = StorageMetricsAggregator(db, days=days)
    
    try:
        metrics = await aggregator.get_metrics()
        logger.info(
            f"[storage_metrics] "
            f"ghost_files={metrics.ghost_files_count} "
            f"total_bytes={metrics.current.total_bytes_db} "
            f"history_days={metrics.history.days_available}"
        )
        return metrics
    except SSOTMissingError as e:
        logger.error(f"[storage_metrics] SSOT missing: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception(f"[storage_metrics] Error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving storage metrics",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CAPTURE SNAPSHOT ENDPOINT (for external cron)
# ═══════════════════════════════════════════════════════════════════════════════

capture_router = APIRouter(
    prefix="/_internal/admin/storage",
    tags=["admin-storage-cron"],
)


@capture_router.post(
    "/capture-snapshot",
    response_model=CaptureSnapshotResponse,
    dependencies=[Depends(require_internal_service_token)],
)
async def capture_storage_snapshot(
    db: AsyncSession = Depends(get_db),
):
    """
    Capture daily storage snapshot.
    
    Protected by internal service token (not JWT).
    Called by external cron (Railway/GitHub Actions) daily.
    
    Recommended schedule: Daily at 02:00 UTC
    RRULE: FREQ=DAILY;BYHOUR=2;BYMINUTE=0
    
    Calls kpis.fn_capture_storage_snapshot() which:
    - Validates SSOT (fail-fast)
    - Reads v_kpis_storage_snapshot
    - Counts ghost files
    - Upserts into kpis.storage_daily_snapshots
    """
    # Start job execution tracking
    tracker = JobExecutionTracker(
        db=db,
        job_id="capture_storage_snapshot",
        job_type="cron_external",
        module="storage",
    )
    await tracker.start()
    
    try:
        # Check if function exists
        q_check = text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_proc p
                JOIN pg_namespace n ON p.pronamespace = n.oid
                WHERE n.nspname = 'kpis'
                  AND p.proname = 'fn_capture_storage_snapshot'
            ) AS exists
        """)
        res_check = await db.execute(q_check)
        if not res_check.scalar():
            await tracker.finish_failed("fn_capture_storage_snapshot not installed")
            raise HTTPException(
                status_code=500,
                detail="kpis.fn_capture_storage_snapshot not installed. Run migrations."
            )
        
        # Call the capture function
        q = text("SELECT kpis.fn_capture_storage_snapshot() AS result")
        res = await db.execute(q)
        result = res.scalar()
        
        await db.commit()
        
        # Track success
        await tracker.finish_success({
            "ghost_files_count": result.get("ghost_files_count", 0) if result else 0,
            "total_bytes_db": result.get("total_bytes_db", 0) if result else 0,
        })
        
        logger.info(f"[capture_snapshot] Success: {result}")
        
        return CaptureSnapshotResponse(
            success=result.get("success", False) if result else False,
            day=result.get("day", date.today().isoformat()) if result else date.today().isoformat(),
            ghost_files_count=result.get("ghost_files_count", 0) if result else 0,
            total_bytes_db=result.get("total_bytes_db", 0) if result else 0,
            message="Snapshot captured successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[capture_snapshot] Error: {e}")
        await tracker.finish_failed(str(e)[:500])
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error capturing snapshot: {str(e)}",
        )


# Fin del archivo
