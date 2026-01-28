# -*- coding: utf-8 -*-
"""
backend/app/modules/admin/routes/projects_files_business_routes.py

Admin endpoints for Projects/Files Business metrics (NEGOCIO).

Exposes read-only JSON endpoints for the admin dashboard:
- GET /_internal/admin/projects-files/business - Summary with KPIs + daily series

No operational metrics here - those go in a separate routes file.

Author: DoxAI
Created: 2026-01-23
"""
import logging
from datetime import date, datetime, timezone
from typing import List, Optional

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

class DailyProjectActivity(BaseModel):
    """Daily project activity data point."""
    day: str = Field(..., description="Date in YYYY-MM-DD format")
    created: int = Field(0, description="Projects created on this day")
    ready: int = Field(0, description="Projects reaching READY state on this day")


class DailyFileActivity(BaseModel):
    """Daily file activity data point."""
    day: str = Field(..., description="Date in YYYY-MM-DD format")
    uploaded: int = Field(0, description="Input files uploaded on this day")
    generated: int = Field(0, description="Product files generated on this day")


class DailyActiveUsers(BaseModel):
    """Daily active users data point."""
    day: str = Field(..., description="Date in YYYY-MM-DD format")
    users: int = Field(0, description="Unique users with file activity on this day")


class ProjectsFilesBusinessSummary(BaseModel):
    """
    Summary of Projects/Files Business metrics for admin dashboard.
    
    KPIs + daily series for charts.
    No operational metrics (storage, errors, latency) - those are separate.
    
    v2 (2026-01-28): Added projects_active, projects_closed, projects_active_with_files,
    files_processed, files_in_custody, files_deleted for complete lifecycle visibility.
    """
    # ─────────────────────────────────────────────────────────────
    # KPIs - Projects (lifecycle snapshot at to_date)
    # ─────────────────────────────────────────────────────────────
    projects_created: int = Field(0, description="Projects created in period")
    projects_active: int = Field(0, description="Projects with status='in_process' at to_date")
    projects_closed: int = Field(0, description="Projects with status='closed' at to_date")
    projects_active_with_files: int = Field(
        0, 
        description="Active projects with at least one input file (product files not required)"
    )
    
    # ─────────────────────────────────────────────────────────────
    # KPIs - Files (lifecycle in period)
    # ─────────────────────────────────────────────────────────────
    files_uploaded: int = Field(0, description="Input files uploaded in period")
    files_processed: int = Field(
        0, 
        description="Input files with input_file_status IN ('parsed','vectorized') uploaded in period"
    )
    files_generated: int = Field(0, description="Product files generated in period")
    files_in_custody: int = Field(
        0, 
        description="Files (input+product) with storage_state='present' at to_date"
    )
    files_deleted: int = Field(
        0, 
        description="Files (input+product) with storage_state='invalidated' in period"
    )
    
    # ─────────────────────────────────────────────────────────────
    # KPIs - Users & Credits
    # ─────────────────────────────────────────────────────────────
    active_users_files: int = Field(0, description="Unique users with file activity in period")
    credits_consumed_files: Optional[int] = Field(
        None, 
        description="Credits consumed by Files module (null = pending implementation)"
    )
    
    # ─────────────────────────────────────────────────────────────
    # Range
    # ─────────────────────────────────────────────────────────────
    range_from: str = Field(..., description="Start date (YYYY-MM-DD)")
    range_to: str = Field(..., description="End date (YYYY-MM-DD)")
    
    # ─────────────────────────────────────────────────────────────
    # Daily Series for Charts
    # ─────────────────────────────────────────────────────────────
    project_activity_series: List[DailyProjectActivity] = Field(
        default_factory=list,
        description="Daily series: projects created vs ready"
    )
    file_activity_series: List[DailyFileActivity] = Field(
        default_factory=list,
        description="Daily series: files uploaded vs generated"
    )
    active_users_series: List[DailyActiveUsers] = Field(
        default_factory=list,
        description="Daily series: unique active users"
    )
    
    # ─────────────────────────────────────────────────────────────
    # Meta
    # ─────────────────────────────────────────────────────────────
    generated_at: str = Field(..., description="ISO timestamp of generation")


# ═══════════════════════════════════════════════════════════════════════════════
# AGGREGATOR
# ═══════════════════════════════════════════════════════════════════════════════

class SSOTMissingError(Exception):
    """Raised when a required SSOT object (table/view) is missing."""
    pass


def _generate_date_range(from_date: date, to_date: date) -> List[str]:
    """Generate a list of all dates in the range (inclusive) as YYYY-MM-DD strings."""
    from datetime import timedelta
    dates = []
    current = from_date
    while current <= to_date:
        dates.append(current.isoformat())
        current += timedelta(days=1)
    return dates


# Module-level flag to avoid log spam (once per process)
_module_column_logged: bool = False


class ProjectsFilesBusinessAggregator:
    """
    Aggregator for Projects/Files Business metrics.
    
    Executes SSOT queries against existing DB tables:
    - projects (created_at)
    - kpis.mv_projects_ready_lead_time_daily (ready_count, day)
    - input_files (input_file_uploaded_at)
    - product_file_activity (event_type, event_at, auth_user_id)
    - credit_transactions (module field - pending)
    
    IMPORTANT: If a required SSOT object is missing, this aggregator raises
    SSOTMissingError rather than silently returning 0.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self._module_column_exists: Optional[bool] = None  # Cached per aggregator instance

    async def get_summary(
        self, 
        from_date: date, 
        to_date: date
    ) -> ProjectsFilesBusinessSummary:
        """
        Get complete business summary for the given date range.
        
        Args:
            from_date: Start date (inclusive)
            to_date: End date (inclusive)
            
        Returns:
            ProjectsFilesBusinessSummary with KPIs and daily series
            
        Raises:
            SSOTMissingError: If required tables/views are not installed
        """
        # Validate SSOT objects exist before querying
        await self._validate_ssot_objects()
        
        # Generate complete date range for series (no gaps)
        all_days = _generate_date_range(from_date, to_date)
        
        # Convert to_date to exclusive (next day) for consistent queries
        from datetime import timedelta
        to_date_exclusive = to_date + timedelta(days=1)
        
        # Keep string versions for response
        from_str = from_date.isoformat()
        to_str = to_date.isoformat()
        
        # asyncpg requires datetime objects, not strings
        # Convert date to datetime at 00:00:00 UTC (timezone-aware) for timestamptz queries
        from_dt = datetime.combine(from_date, datetime.min.time(), tzinfo=timezone.utc)
        to_exclusive_dt = datetime.combine(to_date_exclusive, datetime.min.time(), tzinfo=timezone.utc)
        
        # Execute all queries with datetime objects
        kpis = await self._get_kpis(from_dt, to_exclusive_dt, from_date, to_date_exclusive)
        projects_lifecycle = await self._get_projects_lifecycle_snapshot(to_date)
        files_lifecycle = await self._get_files_lifecycle(from_dt, to_exclusive_dt, to_date)
        project_series = await self._get_project_activity_series(from_dt, to_exclusive_dt, from_date, to_date_exclusive, all_days)
        file_series = await self._get_file_activity_series(from_dt, to_exclusive_dt, all_days)
        users_series = await self._get_active_users_series(from_dt, to_exclusive_dt, all_days)
        credits = await self._get_credits_consumed_files(from_dt, to_exclusive_dt)
        
        return ProjectsFilesBusinessSummary(
            # Projects
            projects_created=kpis["projects_created"],
            projects_active=projects_lifecycle["active"],
            projects_closed=projects_lifecycle["closed"],
            projects_active_with_files=projects_lifecycle["active_with_files"],
            # Files
            files_uploaded=kpis["files_uploaded"],
            files_processed=files_lifecycle["processed"],
            files_generated=kpis["files_generated"],
            files_in_custody=files_lifecycle["in_custody"],
            files_deleted=files_lifecycle["deleted"],
            # Users & Credits
            active_users_files=kpis["active_users_files"],
            credits_consumed_files=credits,
            # Range
            range_from=from_str,
            range_to=to_str,
            # Series
            project_activity_series=project_series,
            file_activity_series=file_series,
            active_users_series=users_series,
            generated_at=datetime.utcnow().isoformat() + "Z",
        )
    
    async def _validate_ssot_objects(self) -> None:
        """
        Validate that all required SSOT objects exist.
        
        Note: kpis.mv_projects_ready_lead_time_daily is OPTIONAL (only used for daily chart).
        Panel de Negocio no longer requires projects_ready KPI as primary metric.
        
        Raises:
            SSOTMissingError: If any REQUIRED object is missing
        """
        # Check kpis.mv_projects_ready_lead_time_daily - OPTIONAL (warning only)
        # This view is only used for the daily "ready" chart, not required for KPIs
        q_kpis_view = text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.views
                WHERE table_schema = 'kpis' 
                  AND table_name = 'mv_projects_ready_lead_time_daily'
            ) AS exists
        """)
        res = await self.db.execute(q_kpis_view)
        if not res.scalar():
            logger.warning(
                "OPTIONAL: kpis.mv_projects_ready_lead_time_daily view not installed. "
                "Daily 'ready' chart will show 0s. Run database/projects/07_metrics/01_kpis_projects.sql to enable."
            )
            # Store flag for later use in series query
            self._kpis_view_available = False
        else:
            self._kpis_view_available = True
        
        # Check public.product_file_activity - REQUIRED
        q_activity_table = text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' 
                  AND table_name = 'product_file_activity'
            ) AS exists
        """)
        res = await self.db.execute(q_activity_table)
        if not res.scalar():
            logger.error("SSOT missing: public.product_file_activity table not installed")
            raise SSOTMissingError(
                "public.product_file_activity table not installed. "
                "Run database/files/02_tables/05_product_file_activity.sql"
            )
    
    async def _get_kpis(
        self, 
        from_dt: datetime, 
        to_dt: datetime,
        from_date: date,
        to_date_exclusive: date,
    ) -> dict:
        """
        Get aggregate KPIs for the period.
        
        Args:
            from_dt: Start datetime for timestamptz queries
            to_dt: Exclusive end datetime for timestamptz queries
            from_date: Start date for date queries
            to_date_exclusive: Exclusive end date for date queries
        """
        # Projects created - use datetime for timestamptz column
        q1 = text("""
            SELECT COUNT(*) as cnt
            FROM public.projects
            WHERE created_at >= :from_date
              AND created_at < :to_date
        """)
        res1 = await self.db.execute(q1, {"from_date": from_dt, "to_date": to_dt})
        projects_created = int(res1.scalar() or 0)
        
        # Files uploaded - use datetime for timestamptz column
        q3 = text("""
            SELECT COUNT(*) as cnt
            FROM public.input_files
            WHERE input_file_uploaded_at >= :from_date
              AND input_file_uploaded_at < :to_date
        """)
        res3 = await self.db.execute(q3, {"from_date": from_dt, "to_date": to_dt})
        files_uploaded = int(res3.scalar() or 0)
        
        # Files generated - use datetime for timestamptz column
        q4 = text("""
            SELECT COUNT(*) as cnt
            FROM public.product_file_activity
            WHERE event_type = 'generated'
              AND event_at >= :from_date
              AND event_at < :to_date
        """)
        res4 = await self.db.execute(q4, {"from_date": from_dt, "to_date": to_dt})
        files_generated = int(res4.scalar() or 0)
        
        # Active users - use datetime for timestamptz column
        q5 = text("""
            SELECT COUNT(DISTINCT auth_user_id) as cnt
            FROM public.product_file_activity
            WHERE event_at >= :from_date
              AND event_at < :to_date
        """)
        res5 = await self.db.execute(q5, {"from_date": from_dt, "to_date": to_dt})
        active_users = int(res5.scalar() or 0)
        
        return {
            "projects_created": projects_created,
            "files_uploaded": files_uploaded,
            "files_generated": files_generated,
            "active_users_files": active_users,
        }
    
    async def _get_projects_lifecycle_snapshot(self, to_date: date) -> dict:
        """
        Get projects lifecycle snapshot as of to_date.
        
        Definition (user-specified SSOT):
        - projects_active: status='in_process' at to_date
        - projects_closed: status='closed' at to_date
        - projects_active_with_files: active projects with ≥1 input file (product files NOT required)
        
        Args:
            to_date: Snapshot date (inclusive)
        """
        # Convert to datetime for timestamptz column (end of day)
        from datetime import timedelta
        to_dt = datetime.combine(to_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
        
        # Projects active (status='in_process' and created by to_date)
        q_active = text("""
            SELECT COUNT(*) as cnt
            FROM public.projects
            WHERE status = 'in_process'
              AND created_at < :to_date
        """)
        res_active = await self.db.execute(q_active, {"to_date": to_dt})
        active = int(res_active.scalar() or 0)
        
        # Projects closed (status='closed' and closed_at by to_date)
        q_closed = text("""
            SELECT COUNT(*) as cnt
            FROM public.projects
            WHERE status = 'closed'
              AND closed_at IS NOT NULL
              AND closed_at < :to_date
        """)
        res_closed = await self.db.execute(q_closed, {"to_date": to_dt})
        closed = int(res_closed.scalar() or 0)
        
        # Active projects with files (has input_files - product files NOT required per SSOT)
        q_with_files = text("""
            SELECT COUNT(DISTINCT p.id) as cnt
            FROM public.projects p
            WHERE p.status = 'in_process'
              AND p.created_at < :to_date
              AND EXISTS (
                SELECT 1 FROM public.input_files i
                WHERE i.project_id = p.id
                  AND i.input_file_uploaded_at < :to_date
              )
        """)
        res_with_files = await self.db.execute(q_with_files, {"to_date": to_dt})
        active_with_files = int(res_with_files.scalar() or 0)
        
        return {
            "active": active,
            "closed": closed,
            "active_with_files": active_with_files,
        }
    
    async def _get_files_lifecycle(
        self, 
        from_dt: datetime, 
        to_dt: datetime,
        to_date: date,
    ) -> dict:
        """
        Get files lifecycle metrics.
        
        SSOT Definition (2026-01-28):
        - files_processed: input_files WHERE input_file_status IN ('parsed','vectorized')
          Uses input_file_uploaded_at since no processing_completed_at column exists.
          Note: This counts files uploaded in period that have completed processing.
        - files_in_custody: input_files + product_files with storage_state='present' at to_date
        - files_deleted: input_files + product_files with storage_state IN ('missing','invalidated')
          where invalidated_at in period
        
        Args:
            from_dt: Start datetime for timestamptz queries
            to_dt: Exclusive end datetime for timestamptz queries
            to_date: Snapshot date for custody count
        """
        from datetime import timedelta
        to_snapshot_dt = datetime.combine(to_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
        
        # SSOT: files_processed = input_file_status IN ('parsed','vectorized')
        # Temporal window: input_file_uploaded_at (no processing_completed_at exists)
        # Limitation: Counts files UPLOADED in period that NOW have completed status
        q_processed = text("""
            SELECT COUNT(*) as cnt
            FROM public.input_files
            WHERE input_file_status IN ('parsed', 'vectorized')
              AND input_file_uploaded_at >= :from_date
              AND input_file_uploaded_at < :to_date
        """)
        res_processed = await self.db.execute(q_processed, {"from_date": from_dt, "to_date": to_dt})
        processed = int(res_processed.scalar() or 0)
        
        # Files in custody (storage_state='present' at to_date)
        q_custody_input = text("""
            SELECT COUNT(*) as cnt
            FROM public.input_files
            WHERE storage_state = 'present'
              AND input_file_uploaded_at < :to_date
        """)
        res_custody_input = await self.db.execute(q_custody_input, {"to_date": to_snapshot_dt})
        custody_input = int(res_custody_input.scalar() or 0)
        
        q_custody_product = text("""
            SELECT COUNT(*) as cnt
            FROM public.product_files
            WHERE storage_state = 'present'
              AND product_file_generated_at < :to_date
        """)
        res_custody_product = await self.db.execute(q_custody_product, {"to_date": to_snapshot_dt})
        custody_product = int(res_custody_product.scalar() or 0)
        
        files_in_custody = custody_input + custody_product
        
        # Files deleted (storage_state in 'missing','invalidated' with invalidated_at in period)
        # SSOT: invalidated_at column is canonical timestamp for soft-delete
        q_deleted_input = text("""
            SELECT COUNT(*) as cnt
            FROM public.input_files
            WHERE storage_state IN ('missing', 'invalidated')
              AND invalidated_at IS NOT NULL
              AND invalidated_at >= :from_date
              AND invalidated_at < :to_date
        """)
        res_deleted_input = await self.db.execute(q_deleted_input, {"from_date": from_dt, "to_date": to_dt})
        deleted_input = int(res_deleted_input.scalar() or 0)
        
        q_deleted_product = text("""
            SELECT COUNT(*) as cnt
            FROM public.product_files
            WHERE storage_state IN ('missing', 'invalidated')
              AND invalidated_at IS NOT NULL
              AND invalidated_at >= :from_date
              AND invalidated_at < :to_date
        """)
        res_deleted_product = await self.db.execute(q_deleted_product, {"from_date": from_dt, "to_date": to_dt})
        deleted_product = int(res_deleted_product.scalar() or 0)
        
        files_deleted = deleted_input + deleted_product
        
        return {
            "processed": processed,
            "in_custody": files_in_custody,
            "deleted": files_deleted,
        }
    
    async def _get_project_activity_series(
        self, 
        from_dt: datetime, 
        to_dt: datetime, 
        from_date: date,
        to_date_exclusive: date,
        all_days: List[str],
    ) -> List[DailyProjectActivity]:
        """Get daily project activity series with complete date range."""
        # Projects created per day - use datetime for timestamptz column
        q_created = text("""
            SELECT DATE(created_at) as day, COUNT(*) as cnt
            FROM public.projects
            WHERE created_at >= :from_date
              AND created_at < :to_date
            GROUP BY DATE(created_at)
        """)
        res_created = await self.db.execute(q_created, {"from_date": from_dt, "to_date": to_dt})
        created_map = {str(row.day): int(row.cnt) for row in res_created.fetchall()}
        
        # Projects ready per day (from OPTIONAL view) - use date for date column
        # If view not available, skip query and use empty map
        ready_map: dict = {}
        if getattr(self, '_kpis_view_available', True):
            try:
                q_ready = text("""
                    SELECT day, ready_count
                    FROM kpis.mv_projects_ready_lead_time_daily
                    WHERE day >= :from_date
                      AND day < :to_date
                """)
                res_ready = await self.db.execute(q_ready, {"from_date": from_date, "to_date": to_date_exclusive})
                ready_map = {str(row.day): int(row.ready_count or 0) for row in res_ready.fetchall()}
            except Exception as e:
                logger.warning(f"Could not fetch ready series from kpis view: {e}")
                ready_map = {}
        
        # Build complete series with all days (fill zeros for missing days)
        return [
            DailyProjectActivity(
                day=day,
                created=created_map.get(day, 0),
                ready=ready_map.get(day, 0),
            )
            for day in all_days
        ]
    
    async def _get_file_activity_series(
        self, 
        from_dt: datetime, 
        to_dt: datetime, 
        all_days: List[str],
    ) -> List[DailyFileActivity]:
        """Get daily file activity series with complete date range."""
        # Files uploaded per day - use datetime for timestamptz column
        q_uploaded = text("""
            SELECT DATE(input_file_uploaded_at) as day, COUNT(*) as cnt
            FROM public.input_files
            WHERE input_file_uploaded_at >= :from_date
              AND input_file_uploaded_at < :to_date
            GROUP BY DATE(input_file_uploaded_at)
        """)
        res_uploaded = await self.db.execute(q_uploaded, {"from_date": from_dt, "to_date": to_dt})
        uploaded_map = {str(row.day): int(row.cnt) for row in res_uploaded.fetchall()}
        
        # Files generated per day - use datetime for timestamptz column
        q_generated = text("""
            SELECT DATE(event_at) as day, COUNT(*) as cnt
            FROM public.product_file_activity
            WHERE event_type = 'generated'
              AND event_at >= :from_date
              AND event_at < :to_date
            GROUP BY DATE(event_at)
        """)
        res_generated = await self.db.execute(q_generated, {"from_date": from_dt, "to_date": to_dt})
        generated_map = {str(row.day): int(row.cnt) for row in res_generated.fetchall()}
        
        # Build complete series with all days (fill zeros for missing days)
        return [
            DailyFileActivity(
                day=day,
                uploaded=uploaded_map.get(day, 0),
                generated=generated_map.get(day, 0),
            )
            for day in all_days
        ]
    
    async def _get_active_users_series(
        self, 
        from_dt: datetime, 
        to_dt: datetime, 
        all_days: List[str],
    ) -> List[DailyActiveUsers]:
        """Get daily active users series with complete date range."""
        # Use datetime for timestamptz column
        q = text("""
            SELECT DATE(event_at) as day, COUNT(DISTINCT auth_user_id) as cnt
            FROM public.product_file_activity
            WHERE event_at >= :from_date
              AND event_at < :to_date
            GROUP BY DATE(event_at)
        """)
        res = await self.db.execute(q, {"from_date": from_dt, "to_date": to_dt})
        users_map = {str(row.day): int(row.cnt) for row in res.fetchall()}
        
        # Build complete series with all days (fill zeros for missing days)
        return [
            DailyActiveUsers(day=day, users=users_map.get(day, 0))
            for day in all_days
        ]
    
    async def _check_module_column_exists(self) -> bool:
        """
        Check if 'module' column exists in credit_transactions table.
        
        Uses information_schema for reliable schema introspection.
        Result is cached per-request to avoid repeated queries.
        Logs INFO once per process (not per request) to avoid log spam.
        """
        global _module_column_logged
        
        if self._module_column_exists is not None:
            return self._module_column_exists
        
        q = text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'credit_transactions'
                  AND column_name = 'module'
            ) AS exists
        """)
        res = await self.db.execute(q)
        exists = bool(res.scalar())
        self._module_column_exists = exists
        
        # Log once per process, not per request
        if not exists and not _module_column_logged:
            logger.info(
                "[credits_consumed_files] column 'module' not found in credit_transactions. "
                "Run migration 18_credit_transactions_add_module.sql to enable this metric."
            )
            _module_column_logged = True
        
        return exists
    
    async def _get_credits_consumed_files(
        self, 
        from_dt: datetime, 
        to_dt: datetime,
    ) -> Optional[int]:
        """
        Get credits consumed by Files module.
        
        Returns:
        - int >= 0 when 'module' column exists (0 means no consumption in period)
        - None only if 'module' column doesn't exist (migration pending)
        
        SSOT: Only queries when module column exists. Does NOT infer 'files' 
        from other fields.
        """
        # Check schema first - avoids UndefinedColumnError
        if not await self._check_module_column_exists():
            return None
        
        try:
            # Use datetime for timestamptz column
            # SUM(ABS(credits_delta)) because debits are negative
            q = text("""
                SELECT COALESCE(SUM(ABS(credits_delta)), 0) as total
                FROM public.credit_transactions
                WHERE module = 'files'
                  AND tx_type = 'debit'
                  AND created_at >= :from_date
                  AND created_at < :to_date
            """)
            res = await self.db.execute(q, {"from_date": from_dt, "to_date": to_dt})
            total = int(res.scalar() or 0)
            
            # Return actual value (even if 0 - that's valid "no consumption")
            return total
        except Exception as e:
            # Unexpected error - log as warning and return None
            logger.warning(f"[credits_consumed_files] query failed: {e}")
            return None


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTER
# ═══════════════════════════════════════════════════════════════════════════════

router = APIRouter(
    prefix="/_internal/admin/projects-files",
    tags=["admin-projects-files-business"],
    dependencies=[Depends(require_admin_strict)],
)


@router.get("/business", response_model=ProjectsFilesBusinessSummary)
async def get_projects_files_business_summary(
    from_date: str = Query(
        ..., 
        alias="from",
        description="Start date (YYYY-MM-DD)",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    to_date: str = Query(
        ...,
        alias="to", 
        description="End date (YYYY-MM-DD)",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Get Projects/Files Business metrics summary.
    
    Returns KPIs and daily series for the admin dashboard charts.
    
    SSOT Queries:
    - projects_created: COUNT(*) FROM projects WHERE created_at in range
    - projects_ready: SUM(ready_count) FROM kpis.mv_projects_ready_lead_time_daily
    - files_uploaded: COUNT(*) FROM input_files WHERE input_file_uploaded_at in range
    - files_generated: COUNT(*) FROM product_file_activity WHERE event_type='generated'
    - active_users_files: COUNT(DISTINCT auth_user_id) FROM product_file_activity
    - credits_consumed_files: SUM(credits_delta) FROM credit_transactions WHERE module='files'
      (returns null if module field not populated)
    """
    try:
        from_dt = date.fromisoformat(from_date)
        to_dt = date.fromisoformat(to_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    
    if from_dt > to_dt:
        raise HTTPException(status_code=400, detail="from_date must be <= to_date")
    
    aggregator = ProjectsFilesBusinessAggregator(db)
    
    try:
        summary = await aggregator.get_summary(from_dt, to_dt)
        logger.info(
            f"[projects_files_business] range={from_date}..{to_date} "
            f"projects_created={summary.projects_created} "
            f"files_uploaded={summary.files_uploaded} "
            f"active_users={summary.active_users_files}"
        )
        return summary
    except SSOTMissingError as e:
        # Explicit failure when required SSOT objects are missing
        logger.error(f"[projects_files_business] SSOT missing: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"SSOT missing: {str(e)}",
        )
    except Exception as e:
        logger.exception(f"[projects_files_business] Error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving Projects/Files business metrics",
        )


# Fin del archivo backend/app/modules/admin/routes/projects_files_business_routes.py
