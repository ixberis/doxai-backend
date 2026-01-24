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
from datetime import date, datetime
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
    """
    # ─────────────────────────────────────────────────────────────
    # KPIs
    # ─────────────────────────────────────────────────────────────
    projects_created: int = Field(0, description="Projects created in period")
    projects_ready: int = Field(0, description="Projects that reached READY state in period")
    files_uploaded: int = Field(0, description="Input files uploaded in period")
    files_generated: int = Field(0, description="Product files generated in period")
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
        
        from_str = from_date.isoformat()
        to_str = to_date.isoformat()
        to_exclusive_str = to_date_exclusive.isoformat()
        
        # Execute all queries
        kpis = await self._get_kpis(from_str, to_exclusive_str)
        project_series = await self._get_project_activity_series(from_str, to_exclusive_str, all_days)
        file_series = await self._get_file_activity_series(from_str, to_exclusive_str, all_days)
        users_series = await self._get_active_users_series(from_str, to_exclusive_str, all_days)
        credits = await self._get_credits_consumed_files(from_str, to_exclusive_str)
        
        return ProjectsFilesBusinessSummary(
            projects_created=kpis["projects_created"],
            projects_ready=kpis["projects_ready"],
            files_uploaded=kpis["files_uploaded"],
            files_generated=kpis["files_generated"],
            active_users_files=kpis["active_users_files"],
            credits_consumed_files=credits,
            range_from=from_str,
            range_to=to_str,
            project_activity_series=project_series,
            file_activity_series=file_series,
            active_users_series=users_series,
            generated_at=datetime.utcnow().isoformat() + "Z",
        )
    
    async def _validate_ssot_objects(self) -> None:
        """
        Validate that all required SSOT objects exist.
        
        Raises:
            SSOTMissingError: If any required object is missing
        """
        # Check kpis.mv_projects_ready_lead_time_daily
        q_kpis_view = text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.views
                WHERE table_schema = 'kpis' 
                  AND table_name = 'mv_projects_ready_lead_time_daily'
            ) AS exists
        """)
        res = await self.db.execute(q_kpis_view)
        if not res.scalar():
            logger.error("SSOT missing: kpis.mv_projects_ready_lead_time_daily view not installed")
            raise SSOTMissingError(
                "kpis.mv_projects_ready_lead_time_daily view not installed. "
                "Run database/projects/07_metrics/01_kpis_projects.sql"
            )
        
        # Check public.product_file_activity
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
    
    async def _get_kpis(self, from_str: str, to_str: str) -> dict:
        """Get aggregate KPIs for the period."""
        # Projects created
        q1 = text("""
            SELECT COUNT(*) as cnt
            FROM public.projects
            WHERE created_at >= CAST(:from_date AS timestamptz)
              AND created_at < CAST(:to_date AS timestamptz)
        """)
        res1 = await self.db.execute(q1, {"from_date": from_str, "to_date": to_str})
        projects_created = int(res1.scalar() or 0)
        
        # Projects ready (from view - already validated)
        q2 = text("""
            SELECT COALESCE(SUM(ready_count), 0) as cnt
            FROM kpis.mv_projects_ready_lead_time_daily
            WHERE day >= CAST(:from_date AS date)
              AND day < CAST(:to_date AS date)
        """)
        res2 = await self.db.execute(q2, {"from_date": from_str, "to_date": to_str})
        projects_ready = int(res2.scalar() or 0)
        
        # Files uploaded
        q3 = text("""
            SELECT COUNT(*) as cnt
            FROM public.input_files
            WHERE input_file_uploaded_at >= CAST(:from_date AS timestamptz)
              AND input_file_uploaded_at < CAST(:to_date AS timestamptz)
        """)
        res3 = await self.db.execute(q3, {"from_date": from_str, "to_date": to_str})
        files_uploaded = int(res3.scalar() or 0)
        
        # Files generated (product_file_activity - already validated)
        q4 = text("""
            SELECT COUNT(*) as cnt
            FROM public.product_file_activity
            WHERE event_type = 'generated'
              AND event_at >= CAST(:from_date AS timestamptz)
              AND event_at < CAST(:to_date AS timestamptz)
        """)
        res4 = await self.db.execute(q4, {"from_date": from_str, "to_date": to_str})
        files_generated = int(res4.scalar() or 0)
        
        # Active users (distinct auth_user_id - already validated)
        q5 = text("""
            SELECT COUNT(DISTINCT auth_user_id) as cnt
            FROM public.product_file_activity
            WHERE event_at >= CAST(:from_date AS timestamptz)
              AND event_at < CAST(:to_date AS timestamptz)
        """)
        res5 = await self.db.execute(q5, {"from_date": from_str, "to_date": to_str})
        active_users = int(res5.scalar() or 0)
        
        return {
            "projects_created": projects_created,
            "projects_ready": projects_ready,
            "files_uploaded": files_uploaded,
            "files_generated": files_generated,
            "active_users_files": active_users,
        }
    
    async def _get_project_activity_series(
        self, from_str: str, to_str: str, all_days: List[str]
    ) -> List[DailyProjectActivity]:
        """Get daily project activity series with complete date range."""
        # Projects created per day
        q_created = text("""
            SELECT DATE(created_at) as day, COUNT(*) as cnt
            FROM public.projects
            WHERE created_at >= CAST(:from_date AS timestamptz)
              AND created_at < CAST(:to_date AS timestamptz)
            GROUP BY DATE(created_at)
        """)
        res_created = await self.db.execute(q_created, {"from_date": from_str, "to_date": to_str})
        created_map = {str(row.day): int(row.cnt) for row in res_created.fetchall()}
        
        # Projects ready per day (from view - already validated)
        q_ready = text("""
            SELECT day, ready_count
            FROM kpis.mv_projects_ready_lead_time_daily
            WHERE day >= CAST(:from_date AS date)
              AND day < CAST(:to_date AS date)
        """)
        res_ready = await self.db.execute(q_ready, {"from_date": from_str, "to_date": to_str})
        ready_map = {str(row.day): int(row.ready_count or 0) for row in res_ready.fetchall()}
        
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
        self, from_str: str, to_str: str, all_days: List[str]
    ) -> List[DailyFileActivity]:
        """Get daily file activity series with complete date range."""
        # Files uploaded per day
        q_uploaded = text("""
            SELECT DATE(input_file_uploaded_at) as day, COUNT(*) as cnt
            FROM public.input_files
            WHERE input_file_uploaded_at >= CAST(:from_date AS timestamptz)
              AND input_file_uploaded_at < CAST(:to_date AS timestamptz)
            GROUP BY DATE(input_file_uploaded_at)
        """)
        res_uploaded = await self.db.execute(q_uploaded, {"from_date": from_str, "to_date": to_str})
        uploaded_map = {str(row.day): int(row.cnt) for row in res_uploaded.fetchall()}
        
        # Files generated per day (already validated)
        q_generated = text("""
            SELECT DATE(event_at) as day, COUNT(*) as cnt
            FROM public.product_file_activity
            WHERE event_type = 'generated'
              AND event_at >= CAST(:from_date AS timestamptz)
              AND event_at < CAST(:to_date AS timestamptz)
            GROUP BY DATE(event_at)
        """)
        res_generated = await self.db.execute(q_generated, {"from_date": from_str, "to_date": to_str})
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
        self, from_str: str, to_str: str, all_days: List[str]
    ) -> List[DailyActiveUsers]:
        """Get daily active users series with complete date range."""
        q = text("""
            SELECT DATE(event_at) as day, COUNT(DISTINCT auth_user_id) as cnt
            FROM public.product_file_activity
            WHERE event_at >= CAST(:from_date AS timestamptz)
              AND event_at < CAST(:to_date AS timestamptz)
            GROUP BY DATE(event_at)
        """)
        res = await self.db.execute(q, {"from_date": from_str, "to_date": to_str})
        users_map = {str(row.day): int(row.cnt) for row in res.fetchall()}
        
        # Build complete series with all days (fill zeros for missing days)
        return [
            DailyActiveUsers(day=day, users=users_map.get(day, 0))
            for day in all_days
        ]
    
    async def _get_credits_consumed_files(
        self, from_str: str, to_str: str
    ) -> Optional[int]:
        """
        Get credits consumed by Files module.
        
        Returns None if module field is not populated (pending migration).
        """
        try:
            # Check if module column exists and has 'files' values
            q = text("""
                SELECT COALESCE(SUM(ABS(credits_delta)), 0) as total
                FROM public.credit_transactions
                WHERE module = 'files'
                  AND tx_type = 'debit'
                  AND created_at >= CAST(:from_date AS timestamptz)
                  AND created_at < CAST(:to_date AS timestamptz)
            """)
            res = await self.db.execute(q, {"from_date": from_str, "to_date": to_str})
            total = int(res.scalar() or 0)
            
            # If 0, check if any 'files' module entries exist at all
            # If not, return None to indicate "pending implementation"
            if total == 0:
                q_check = text("""
                    SELECT COUNT(*) FROM public.credit_transactions
                    WHERE module = 'files'
                    LIMIT 1
                """)
                res_check = await self.db.execute(q_check)
                has_files = int(res_check.scalar() or 0) > 0
                if not has_files:
                    return None
            
            return total
        except Exception as e:
            # Module column might not exist yet
            logger.warning(f"credits_consumed_files not available: {e}")
            return None


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTER
# ═══════════════════════════════════════════════════════════════════════════════

router = APIRouter(
    prefix="/_internal/admin/projects-files",
    tags=["admin-projects-files"],
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
