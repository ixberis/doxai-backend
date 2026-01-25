# -*- coding: utf-8 -*-
"""
backend/app/modules/admin/routes/projects_files_operational_routes.py

Admin endpoints for Projects/Files Operational metrics (OPERACIÓN).

Exposes read-only JSON endpoints for the admin dashboard:
- GET /_internal/admin/projects-files/operational - DB-sourced operational metrics

Prometheus metrics (deletes, latency, Redis debounce) are consumed via Grafana,
not through this endpoint.

Author: DoxAI
Created: 2026-01-23
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.modules.auth.dependencies import require_admin_strict


logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class StorageSnapshot(BaseModel):
    """Storage metrics from v_kpis_storage_snapshot."""
    total_bytes: int = Field(0, description="Total bytes in storage (from DB)")
    total_size_pretty: str = Field("0 B", description="Human-readable size")
    ssot_objects: int = Field(0, description="Objects following SSOT path")
    legacy_objects: int = Field(0, description="Legacy path objects")
    legacy_status: str = Field("unknown", description="healthy | migrating | needs_attention")
    unique_users: int = Field(0, description="Unique users with files")
    unique_projects: int = Field(0, description="Unique projects with files")
    input_delta: int = Field(0, description="Delta storage vs DB for input files")
    product_delta: int = Field(0, description="Delta storage vs DB for product files")


class GhostFilesMetrics(BaseModel):
    """Ghost files metrics from input_files (legacy: storage_exists)."""
    count: int = Field(0, description="Active files with storage_exists=false")
    status: str = Field("healthy", description="healthy | warning | critical")


class ReconciliationMetrics(BaseModel):
    """
    SSOT reconciliation metrics based on storage_state.
    
    - missing_active: Files marked as 'missing' that are still active (need attention)
    - invalidated: Files already processed by reconciliation job
    """
    input_missing_active: int = Field(0, description="input_files with storage_state='missing' AND active")
    product_missing_active: int = Field(0, description="product_files with storage_state='missing' AND active")
    input_invalidated: int = Field(0, description="input_files with storage_state='invalidated'")
    product_invalidated: int = Field(0, description="product_files with storage_state='invalidated'")


class RedisDebounceHint(BaseModel):
    """
    Hint for Redis debounce status.
    
    Actual metrics come from Prometheus. This is metadata for dashboard.
    """
    prometheus_metrics: list[str] = Field(
        default_factory=lambda: [
            "touch_debounced_allowed_total",
            "touch_debounced_skipped_total",
            "touch_debounced_redis_error_total",
            "touch_debounced_redis_unavailable_total",
        ],
        description="Prometheus metrics to query via Grafana"
    )
    promql_health: str = Field(
        default=(
            "sum(rate(touch_debounced_redis_error_total[5m])) + "
            "sum(rate(touch_debounced_redis_unavailable_total[5m])) == 0 "
            "and sum(rate(touch_debounced_allowed_total[5m])) + "
            "sum(rate(touch_debounced_skipped_total[5m])) > 0"
        ),
        description="PromQL expression for health check (true = healthy)"
    )


class DeletesMetricsHint(BaseModel):
    """
    Hint for delete metrics from Prometheus.
    
    Actual data comes from Prometheus/Grafana. This provides query templates.
    """
    prometheus_metrics: list[str] = Field(
        default_factory=lambda: [
            "files_delete_total",
            "files_delete_latency_seconds",
            "files_delete_partial_failures_total",
            "files_delete_errors_total",
        ],
        description="Prometheus metrics to query via Grafana"
    )
    promql_deletes_24h: str = Field(
        default="sum(increase(files_delete_total[24h])) by (result)",
        description="PromQL for delete counts by result"
    )
    promql_deletes_trend: str = Field(
        default="sum(increase(files_delete_total[1h])) by (file_type, op, result)",
        description="PromQL for hourly trend by dimensions"
    )
    promql_latency_p50: str = Field(
        default=(
            'histogram_quantile(0.5, sum(rate(files_delete_latency_seconds_bucket'
            '{op=~"bulk_delete|cleanup_ghosts"}[5m])) by (le, file_type, op))'
        ),
        description="PromQL for p50 latency (bulk ops)"
    )
    promql_latency_p95: str = Field(
        default=(
            'histogram_quantile(0.95, sum(rate(files_delete_latency_seconds_bucket'
            '{op=~"bulk_delete|cleanup_ghosts"}[5m])) by (le, file_type, op))'
        ),
        description="PromQL for p95 latency (bulk ops)"
    )
    promql_partial_failures_24h: str = Field(
        default="sum(increase(files_delete_partial_failures_total[24h]))",
        description="PromQL for partial failures count"
    )


class ProjectsFilesOperationalSummary(BaseModel):
    """
    Operational metrics summary for admin dashboard.
    
    DB-sourced metrics are included directly.
    Prometheus metrics are provided as PromQL hints for Grafana integration.
    """
    # ─────────────────────────────────────────────────────────────
    # DB-sourced metrics (direct values)
    # ─────────────────────────────────────────────────────────────
    ghost_files: GhostFilesMetrics = Field(
        default_factory=GhostFilesMetrics,
        description="Legacy ghost files metrics from DB (storage_exists=false)"
    )
    reconciliation: ReconciliationMetrics = Field(
        default_factory=ReconciliationMetrics,
        description="SSOT reconciliation metrics (storage_state)"
    )
    storage: StorageSnapshot = Field(
        default_factory=StorageSnapshot,
        description="Storage snapshot from DB"
    )
    
    # ─────────────────────────────────────────────────────────────
    # Prometheus hints (for Grafana integration)
    # ─────────────────────────────────────────────────────────────
    deletes_hint: DeletesMetricsHint = Field(
        default_factory=DeletesMetricsHint,
        description="PromQL hints for delete metrics"
    )
    redis_debounce_hint: RedisDebounceHint = Field(
        default_factory=RedisDebounceHint,
        description="PromQL hints for Redis debounce metrics"
    )
    
    # ─────────────────────────────────────────────────────────────
    # Meta
    # ─────────────────────────────────────────────────────────────
    generated_at: str = Field(..., description="ISO timestamp of generation")
    grafana_required: bool = Field(
        True,
        description="True = Prometheus metrics require Grafana embed"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# AGGREGATOR
# ═══════════════════════════════════════════════════════════════════════════════

class SSOTMissingError(Exception):
    """Raised when a required SSOT object (table/view) is missing."""
    pass


class ProjectsFilesOperationalAggregator:
    """
    Aggregator for Projects/Files Operational metrics.
    
    Queries DB for:
    - Ghost files count (input_files with storage_exists=false)
    - Storage snapshot (v_kpis_storage_snapshot)
    
    Prometheus metrics (deletes, latency, Redis) are NOT queried here.
    They are consumed via Grafana embed in the frontend.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_summary(self) -> ProjectsFilesOperationalSummary:
        """
        Get operational summary with DB metrics.
        
        Returns:
            ProjectsFilesOperationalSummary with DB metrics and Prometheus hints
            
        Raises:
            SSOTMissingError: If required views are not installed
        """
        ghost_files = await self._get_ghost_files_metrics()
        reconciliation = await self._get_reconciliation_metrics()
        storage = await self._get_storage_snapshot()
        
        return ProjectsFilesOperationalSummary(
            ghost_files=ghost_files,
            reconciliation=reconciliation,
            storage=storage,
            deletes_hint=DeletesMetricsHint(),
            redis_debounce_hint=RedisDebounceHint(),
            generated_at=datetime.utcnow().isoformat() + "Z",
            grafana_required=True,
        )
    
    async def _get_ghost_files_metrics(self) -> GhostFilesMetrics:
        """
        Count active ghost files (storage_exists = false).
        
        Ghost file = DB record exists but physical file is missing from storage.
        
        Raises:
            SSOTMissingError: If storage_exists column is missing (fail-fast)
        """
        # Check if storage_exists column exists - fail-fast if missing
        q_check = text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'input_files'
                  AND column_name = 'storage_exists'
            ) AS exists
        """)
        res_check = await self.db.execute(q_check)
        has_column = res_check.scalar()
        
        if not has_column:
            logger.error("SSOT missing: input_files.storage_exists column not installed")
            raise SSOTMissingError(
                "storage_exists column not installed. "
                "Reinstall DB using canonical SQL (database/files/_index_files.sql)."
            )
        
        q = text("""
            SELECT COUNT(*) AS ghost_count
            FROM public.input_files
            WHERE input_file_is_active = true
              AND storage_exists = false
        """)
        res = await self.db.execute(q)
        count = int(res.scalar() or 0)
        
        # Determine status based on count thresholds
        if count == 0:
            status = "healthy"
        elif count < 100:
            status = "warning"
        else:
            status = "critical"
        
        return GhostFilesMetrics(count=count, status=status)
    
    async def _get_reconciliation_metrics(self) -> ReconciliationMetrics:
        """
        Get SSOT reconciliation metrics based on storage_state.
        
        Raises:
            SSOTMissingError: If storage_state column is missing (fail-fast)
        """
        # Check if storage_state column exists in BOTH tables - single optimized query
        q_check = text("""
            SELECT 
                EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'input_files'
                      AND column_name = 'storage_state'
                ) AS has_input,
                EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'product_files'
                      AND column_name = 'storage_state'
                ) AS has_product
        """)
        res_check = await self.db.execute(q_check)
        row = res_check.fetchone()
        has_input_column = row.has_input if row else False
        has_product_column = row.has_product if row else False
        
        if not has_input_column or not has_product_column:
            missing_tables = []
            if not has_input_column:
                missing_tables.append("input_files")
            if not has_product_column:
                missing_tables.append("product_files")
            logger.error(f"SSOT missing: storage_state column not installed in {missing_tables}")
            raise SSOTMissingError(
                "storage_state column not installed. "
                "Reinstall DB using canonical SQL (database/files/_index_files.sql)."
            )
        
        # Query: input missing activos
        q_input_missing = text("""
            SELECT COUNT(*)::int FROM public.input_files 
            WHERE storage_state='missing' 
              AND input_file_is_active=true 
              AND input_file_is_archived=false
        """)
        res_input_missing = await self.db.execute(q_input_missing)
        input_missing_active = int(res_input_missing.scalar() or 0)
        
        # Query: product missing activos
        q_product_missing = text("""
            SELECT COUNT(*)::int FROM public.product_files 
            WHERE storage_state='missing' 
              AND product_file_is_active=true 
              AND product_file_is_archived=false
        """)
        res_product_missing = await self.db.execute(q_product_missing)
        product_missing_active = int(res_product_missing.scalar() or 0)
        
        # Query: input invalidated
        q_input_invalidated = text("""
            SELECT COUNT(*)::int FROM public.input_files 
            WHERE storage_state='invalidated'
        """)
        res_input_invalidated = await self.db.execute(q_input_invalidated)
        input_invalidated = int(res_input_invalidated.scalar() or 0)
        
        # Query: product invalidated
        q_product_invalidated = text("""
            SELECT COUNT(*)::int FROM public.product_files 
            WHERE storage_state='invalidated'
        """)
        res_product_invalidated = await self.db.execute(q_product_invalidated)
        product_invalidated = int(res_product_invalidated.scalar() or 0)
        
        return ReconciliationMetrics(
            input_missing_active=input_missing_active,
            product_missing_active=product_missing_active,
            input_invalidated=input_invalidated,
            product_invalidated=product_invalidated,
        )
    
    async def _get_storage_snapshot(self) -> StorageSnapshot:
        """
        Get storage metrics from v_kpis_storage_snapshot view.
        
        Checks both regular views and materialized views.
        
        Raises:
            SSOTMissingError: If v_kpis_storage_snapshot is missing
        """
        # Check if view OR materialized view exists
        q_check = text("""
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
        res_check = await self.db.execute(q_check)
        has_view = res_check.scalar()
        
        if not has_view:
            logger.error("SSOT missing: v_kpis_storage_snapshot view/matview not installed")
            raise SSOTMissingError(
                "v_kpis_storage_snapshot view not installed. "
                "Reinstall DB using canonical SQL (database/storage/_index_storage.sql)."
            )
        
        q = text("""
            SELECT 
                total_bytes_db,
                total_size_db_pretty,
                ssot_objects,
                legacy_objects,
                legacy_status,
                unique_users,
                unique_projects,
                input_delta_storage_vs_db,
                product_delta_storage_vs_db
            FROM public.v_kpis_storage_snapshot
        """)
        res = await self.db.execute(q)
        row = res.fetchone()
        
        if not row:
            return StorageSnapshot()
        
        return StorageSnapshot(
            total_bytes=int(row.total_bytes_db or 0),
            total_size_pretty=str(row.total_size_db_pretty or "0 B"),
            ssot_objects=int(row.ssot_objects or 0),
            legacy_objects=int(row.legacy_objects or 0),
            legacy_status=str(row.legacy_status or "unknown"),
            unique_users=int(row.unique_users or 0),
            unique_projects=int(row.unique_projects or 0),
            input_delta=int(row.input_delta_storage_vs_db or 0),
            product_delta=int(row.product_delta_storage_vs_db or 0),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTER
# ═══════════════════════════════════════════════════════════════════════════════

router = APIRouter(
    prefix="/_internal/admin/projects-files",
    tags=["admin-projects-files-operational"],
    dependencies=[Depends(require_admin_strict)],
)


@router.get("/operational", response_model=ProjectsFilesOperationalSummary)
async def get_projects_files_operational_summary(
    db: AsyncSession = Depends(get_db),
):
    """
    Get Projects/Files Operational metrics summary.
    
    Returns DB-sourced metrics (ghost files, storage) directly.
    Prometheus metrics (deletes, latency, Redis debounce) are provided
    as PromQL hints for Grafana integration.
    
    SSOT Queries (DB):
    - ghost_files: COUNT(*) FROM input_files WHERE storage_exists=false
    - storage: SELECT * FROM v_kpis_storage_snapshot
    
    Prometheus (via Grafana):
    - files_delete_total{file_type, op, result}
    - files_delete_latency_seconds{file_type, op}
    - files_delete_partial_failures_total{file_type, op}
    - touch_debounced_*{reason}
    """
    aggregator = ProjectsFilesOperationalAggregator(db)
    
    try:
        summary = await aggregator.get_summary()
        logger.info(
            f"[projects_files_operational] "
            f"ghost_files={summary.ghost_files.count} "
            f"reconciliation(missing_input={summary.reconciliation.input_missing_active}, "
            f"missing_product={summary.reconciliation.product_missing_active}, "
            f"invalidated_input={summary.reconciliation.input_invalidated}, "
            f"invalidated_product={summary.reconciliation.product_invalidated}) "
            f"storage_bytes={summary.storage.total_bytes} "
            f"legacy_status={summary.storage.legacy_status}"
        )
        return summary
    except SSOTMissingError as e:
        logger.error(f"[projects_files_operational] SSOT missing: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"SSOT missing: {str(e)}",
        )
    except Exception as e:
        logger.exception(f"[projects_files_operational] Error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving Projects/Files operational metrics",
        )


# Fin del archivo
