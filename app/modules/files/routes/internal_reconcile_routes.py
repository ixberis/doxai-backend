# -*- coding: utf-8 -*-
"""
backend/app/modules/files/routes/internal_reconcile_routes.py

Internal endpoint for BD ↔ Storage reconciliation (RFC-DoxAI-STO-001).

Endpoint:
- POST /_internal/files/reconcile-storage

Purpose:
- Detect records with storage_state='missing' (BD sin objeto físico)
- Optionally invalidate them (storage_state='invalidated')
- Never touches storage, never deletes DB records

Auth: require_internal_service_token (APP_SERVICE_TOKEN)
NOT admin JWT - this is an operational/internal endpoint.

NOTE: Requires DB reinstallation with storage_state column for E2E tests.

Author: DoxAI
Created: 2026-01-25
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.shared.internal_auth import require_internal_service_token


logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST / RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class ReconcileRequest(BaseModel):
    """Request payload for reconciliation endpoint."""
    
    dry_run: bool = Field(
        default=True,
        description="If true, only count eligible records without modifying. Default true."
    )
    scope: Literal["all", "project"] = Field(
        default="all",
        description="'all' = all projects, 'project' = single project"
    )
    project_id: Optional[str] = Field(
        default=None,
        description="Required when scope='project'. UUID of target project."
    )
    limit: int = Field(
        default=5000,
        ge=1,
        le=10000,
        description="Max records to process per table. Default 5000, max 10000."
    )
    confirm: bool = Field(
        default=False,
        description="Must be true when dry_run=false to confirm execution intent."
    )
    
    @field_validator("project_id")
    @classmethod
    def validate_project_id_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate project_id is valid UUID format if provided."""
        if v is not None:
            try:
                UUID(v)
            except ValueError:
                raise ValueError("project_id must be a valid UUID")
        return v
    
    def model_post_init(self, __context) -> None:
        """Cross-field validation after init."""
        # scope=project requires project_id
        if self.scope == "project" and not self.project_id:
            raise ValueError("project_id is required when scope='project'")
        
        # dry_run=false requires confirm=true
        if not self.dry_run and not self.confirm:
            raise ValueError("confirm=true is required when dry_run=false")


class ProjectBreakdown(BaseModel):
    """Breakdown of eligible/invalidated records by project."""
    project_id: str
    input_files: int = 0
    product_files: int = 0


class ReconcileResponse(BaseModel):
    """Response payload for reconciliation endpoint."""
    
    mode: Literal["dry_run", "execute"] = Field(
        ...,
        description="'dry_run' = preview only, 'execute' = changes applied"
    )
    
    # Eligible counts (before action)
    eligible_input_files: int = Field(
        default=0,
        description="Input files with storage_state='missing'"
    )
    eligible_product_files: int = Field(
        default=0,
        description="Product files with storage_state='missing'"
    )
    
    # Invalidated counts (after action, only in execute mode)
    invalidated_input_files: int = Field(
        default=0,
        description="Input files actually invalidated (execute mode only)"
    )
    invalidated_product_files: int = Field(
        default=0,
        description="Product files actually invalidated (execute mode only)"
    )
    
    # Metadata
    limit_per_table: int = Field(
        ...,
        description="Limit applied per table"
    )
    truncated: bool = Field(
        default=False,
        description="True if more records exist beyond limit"
    )
    scope: str = Field(..., description="Scope used: 'all' or 'project'")
    project_id: Optional[str] = Field(
        default=None,
        description="Project ID if scope='project'"
    )
    
    # Breakdown by project (only in dry_run mode with scope='all')
    by_project: list[ProjectBreakdown] = Field(
        default_factory=list,
        description="Breakdown by project (dry_run + scope='all' only)"
    )
    
    # Timestamps
    executed_at: str = Field(..., description="ISO timestamp of execution")


# ═══════════════════════════════════════════════════════════════════════════════
# SQL QUERIES (Postgres-correct CTEs)
# Filtros: solo registros activos y no archivados
# ═══════════════════════════════════════════════════════════════════════════════

# Count eligible records (dry_run) - INPUT FILES - ALL SCOPE (no project filter)
COUNT_ELIGIBLE_INPUT_ALL_SQL = """
SELECT COUNT(*) AS cnt
FROM public.input_files
WHERE storage_state = 'missing'
  AND input_file_is_active = true
  AND input_file_is_archived = false
"""

# Count eligible records (dry_run) - INPUT FILES - PROJECT SCOPE (with project filter)
COUNT_ELIGIBLE_INPUT_PROJECT_SQL = """
SELECT COUNT(*) AS cnt
FROM public.input_files
WHERE storage_state = 'missing'
  AND input_file_is_active = true
  AND input_file_is_archived = false
  AND project_id = CAST(:project_id AS uuid)
"""

# Count eligible records (dry_run) - PRODUCT FILES - ALL SCOPE (no project filter)
COUNT_ELIGIBLE_PRODUCT_ALL_SQL = """
SELECT COUNT(*) AS cnt
FROM public.product_files
WHERE storage_state = 'missing'
  AND product_file_is_active = true
  AND product_file_is_archived = false
"""

# Count eligible records (dry_run) - PRODUCT FILES - PROJECT SCOPE (with project filter)
COUNT_ELIGIBLE_PRODUCT_PROJECT_SQL = """
SELECT COUNT(*) AS cnt
FROM public.product_files
WHERE storage_state = 'missing'
  AND product_file_is_active = true
  AND product_file_is_archived = false
  AND project_id = CAST(:project_id AS uuid)
"""

# Breakdown by project (dry_run + scope='all')
BREAKDOWN_BY_PROJECT_SQL = """
SELECT 
    project_id::text,
    SUM(CASE WHEN table_name = 'input_files' THEN cnt ELSE 0 END)::int AS input_files,
    SUM(CASE WHEN table_name = 'product_files' THEN cnt ELSE 0 END)::int AS product_files
FROM (
    SELECT project_id, 'input_files' AS table_name, COUNT(*) AS cnt
    FROM public.input_files
    WHERE storage_state = 'missing'
      AND input_file_is_active = true
      AND input_file_is_archived = false
    GROUP BY project_id
    UNION ALL
    SELECT project_id, 'product_files' AS table_name, COUNT(*) AS cnt
    FROM public.product_files
    WHERE storage_state = 'missing'
      AND product_file_is_active = true
      AND product_file_is_archived = false
    GROUP BY project_id
) sub
GROUP BY project_id
ORDER BY (SUM(cnt)) DESC
LIMIT 100
"""

# Invalidate input files (execute mode) - ALL SCOPE
# Uses CTE with FOR UPDATE SKIP LOCKED for safe concurrent access
INVALIDATE_INPUT_ALL_SQL = """
WITH elig AS (
    SELECT input_file_id
    FROM public.input_files
    WHERE storage_state = 'missing'
      AND input_file_is_active = true
      AND input_file_is_archived = false
    ORDER BY created_at ASC, input_file_id ASC
    LIMIT :limit
    FOR UPDATE SKIP LOCKED
)
UPDATE public.input_files
SET 
    storage_state = 'invalidated',
    invalidated_at = :now,
    invalidation_reason = 'reconcile_admin',
    updated_at = :now
WHERE input_file_id IN (SELECT input_file_id FROM elig)
RETURNING input_file_id
"""

# Invalidate input files (execute mode) - PROJECT SCOPE
INVALIDATE_INPUT_PROJECT_SQL = """
WITH elig AS (
    SELECT input_file_id
    FROM public.input_files
    WHERE storage_state = 'missing'
      AND input_file_is_active = true
      AND input_file_is_archived = false
      AND project_id = CAST(:project_id AS uuid)
    ORDER BY created_at ASC, input_file_id ASC
    LIMIT :limit
    FOR UPDATE SKIP LOCKED
)
UPDATE public.input_files
SET 
    storage_state = 'invalidated',
    invalidated_at = :now,
    invalidation_reason = 'reconcile_admin',
    updated_at = :now
WHERE input_file_id IN (SELECT input_file_id FROM elig)
RETURNING input_file_id
"""

# Invalidate product files (execute mode) - ALL SCOPE
INVALIDATE_PRODUCT_ALL_SQL = """
WITH elig AS (
    SELECT product_file_id
    FROM public.product_files
    WHERE storage_state = 'missing'
      AND product_file_is_active = true
      AND product_file_is_archived = false
    ORDER BY created_at ASC, product_file_id ASC
    LIMIT :limit
    FOR UPDATE SKIP LOCKED
)
UPDATE public.product_files
SET 
    storage_state = 'invalidated',
    invalidated_at = :now,
    invalidation_reason = 'reconcile_admin',
    updated_at = :now
WHERE product_file_id IN (SELECT product_file_id FROM elig)
RETURNING product_file_id
"""

# Invalidate product files (execute mode) - PROJECT SCOPE
INVALIDATE_PRODUCT_PROJECT_SQL = """
WITH elig AS (
    SELECT product_file_id
    FROM public.product_files
    WHERE storage_state = 'missing'
      AND product_file_is_active = true
      AND product_file_is_archived = false
      AND project_id = CAST(:project_id AS uuid)
    ORDER BY created_at ASC, product_file_id ASC
    LIMIT :limit
    FOR UPDATE SKIP LOCKED
)
UPDATE public.product_files
SET 
    storage_state = 'invalidated',
    invalidated_at = :now,
    invalidation_reason = 'reconcile_admin',
    updated_at = :now
WHERE product_file_id IN (SELECT product_file_id FROM elig)
RETURNING product_file_id
"""


# ═══════════════════════════════════════════════════════════════════════════════
# RECONCILIATION SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

class ReconciliationService:
    """
    Service for BD ↔ Storage reconciliation.
    
    Invariants:
    - Never changes invalidated → present/missing (within this endpoint)
    - Only transitions missing → invalidated
    - Idempotent (running twice yields same result)
    - Never touches storage
    - Never deletes DB records
    - Only processes active, non-archived files
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def reconcile(self, request: ReconcileRequest) -> ReconcileResponse:
        """
        Execute reconciliation based on request parameters.
        
        Args:
            request: Validated ReconcileRequest
            
        Returns:
            ReconcileResponse with counts and metadata
        """
        now = datetime.now(timezone.utc)
        project_id_param = request.project_id if request.scope == "project" else None
        
        logger.info(
            "reconcile_start",
            extra={
                "dry_run": request.dry_run,
                "scope": request.scope,
                "project_id": project_id_param,
                "limit": request.limit,
            }
        )
        
        if request.dry_run:
            return await self._dry_run(request, now, project_id_param)
        else:
            return await self._execute(request, now, project_id_param)
    
    async def _dry_run(
        self,
        request: ReconcileRequest,
        now: datetime,
        project_id: Optional[str],
    ) -> ReconcileResponse:
        """Preview mode: count eligible records without modifying."""
        
        # Select SQL variant based on request.scope
        if request.scope == "all":
            # ALL scope: no params
            res_input = await self.db.execute(text(COUNT_ELIGIBLE_INPUT_ALL_SQL))
            eligible_input = int(res_input.scalar() or 0)
            
            res_product = await self.db.execute(text(COUNT_ELIGIBLE_PRODUCT_ALL_SQL))
            eligible_product = int(res_product.scalar() or 0)
        else:
            # PROJECT scope: project_id param required
            params = {"project_id": request.project_id}
            res_input = await self.db.execute(
                text(COUNT_ELIGIBLE_INPUT_PROJECT_SQL), params
            )
            eligible_input = int(res_input.scalar() or 0)
            
            res_product = await self.db.execute(
                text(COUNT_ELIGIBLE_PRODUCT_PROJECT_SQL), params
            )
            eligible_product = int(res_product.scalar() or 0)
        
        logger.debug(
            "reconcile_eligible",
            extra={
                "eligible_input_files": eligible_input,
                "eligible_product_files": eligible_product,
            }
        )
        
        # Get breakdown by project (only for scope='all')
        by_project: list[ProjectBreakdown] = []
        if request.scope == "all" and (eligible_input > 0 or eligible_product > 0):
            res_breakdown = await self.db.execute(text(BREAKDOWN_BY_PROJECT_SQL))
            rows = res_breakdown.fetchall()
            by_project = [
                ProjectBreakdown(
                    project_id=str(row.project_id),
                    input_files=int(row.input_files or 0),
                    product_files=int(row.product_files or 0),
                )
                for row in rows
            ]
        
        # Check if truncated
        truncated = (
            eligible_input > request.limit or 
            eligible_product > request.limit
        )
        
        return ReconcileResponse(
            mode="dry_run",
            eligible_input_files=eligible_input,
            eligible_product_files=eligible_product,
            invalidated_input_files=0,
            invalidated_product_files=0,
            limit_per_table=request.limit,
            truncated=truncated,
            scope=request.scope,
            project_id=project_id,
            by_project=by_project,
            executed_at=now.isoformat(),
        )
    
    async def _execute(
        self,
        request: ReconcileRequest,
        now: datetime,
        project_id: Optional[str],
    ) -> ReconcileResponse:
        """Execute mode: invalidate missing records."""
        
        # Select SQL variant based on request.scope
        if request.scope == "all":
            # ALL scope: no project_id param
            base_params = {"limit": request.limit, "now": now}
            
            # Get eligible counts (before mutation)
            res_input_count = await self.db.execute(text(COUNT_ELIGIBLE_INPUT_ALL_SQL))
            eligible_input = int(res_input_count.scalar() or 0)
            
            res_product_count = await self.db.execute(text(COUNT_ELIGIBLE_PRODUCT_ALL_SQL))
            eligible_product = int(res_product_count.scalar() or 0)
            
            # Invalidate files
            res_input = await self.db.execute(text(INVALIDATE_INPUT_ALL_SQL), base_params)
            invalidated_input_ids = res_input.fetchall()
            invalidated_input = len(invalidated_input_ids)
            
            res_product = await self.db.execute(text(INVALIDATE_PRODUCT_ALL_SQL), base_params)
            invalidated_product_ids = res_product.fetchall()
            invalidated_product = len(invalidated_product_ids)
        else:
            # PROJECT scope: project_id param required
            params = {"project_id": request.project_id, "limit": request.limit, "now": now}
            
            # Get eligible counts (before mutation)
            res_input_count = await self.db.execute(
                text(COUNT_ELIGIBLE_INPUT_PROJECT_SQL), {"project_id": request.project_id}
            )
            eligible_input = int(res_input_count.scalar() or 0)
            
            res_product_count = await self.db.execute(
                text(COUNT_ELIGIBLE_PRODUCT_PROJECT_SQL), {"project_id": request.project_id}
            )
            eligible_product = int(res_product_count.scalar() or 0)
            
            # Invalidate files
            res_input = await self.db.execute(text(INVALIDATE_INPUT_PROJECT_SQL), params)
            invalidated_input_ids = res_input.fetchall()
            invalidated_input = len(invalidated_input_ids)
            
            res_product = await self.db.execute(text(INVALIDATE_PRODUCT_PROJECT_SQL), params)
            invalidated_product_ids = res_product.fetchall()
            invalidated_product = len(invalidated_product_ids)
        
        # Commit transaction
        await self.db.commit()
        
        logger.info(
            "reconcile_execute",
            extra={
                "eligible_input_files": eligible_input,
                "eligible_product_files": eligible_product,
                "invalidated_input_files": invalidated_input,
                "invalidated_product_files": invalidated_product,
                "scope": request.scope,
                "project_id": project_id,
            }
        )
        
        # Check if truncated
        truncated = (
            eligible_input > request.limit or 
            eligible_product > request.limit
        )
        
        return ReconcileResponse(
            mode="execute",
            eligible_input_files=eligible_input,
            eligible_product_files=eligible_product,
            invalidated_input_files=invalidated_input,
            invalidated_product_files=invalidated_product,
            limit_per_table=request.limit,
            truncated=truncated,
            scope=request.scope,
            project_id=project_id,
            by_project=[],  # Not provided in execute mode
            executed_at=now.isoformat(),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTER
# Auth: require_internal_service_token (APP_SERVICE_TOKEN)
# ═══════════════════════════════════════════════════════════════════════════════

router = APIRouter(
    prefix="/_internal/files",
    tags=["internal-files-reconcile"],
    dependencies=[Depends(require_internal_service_token)],
)


@router.post(
    "/reconcile-storage",
    response_model=ReconcileResponse,
    summary="Reconcile BD ↔ Storage (RFC-DoxAI-STO-001)",
    description="""
    Detect and optionally invalidate records with storage_state='missing'.
    
    **Auth:** Internal service token (APP_SERVICE_TOKEN via X-Service-Token header)
    
    **Modes:**
    - `dry_run=true` (default): Preview eligible records without changes
    - `dry_run=false, confirm=true`: Execute invalidation
    
    **Scopes:**
    - `scope='all'`: Process all projects
    - `scope='project'`: Process single project (requires project_id)
    
    **Behavior:**
    - Only processes active, non-archived files
    - Only transitions `missing` → `invalidated`
    - Never changes `invalidated` → `present`/`missing`
    - Never touches storage
    - Never deletes DB records
    - Idempotent (running twice yields same result)
    
    **Limits:**
    - `limit` applies per table (input_files, product_files)
    - Max 10,000 records per table per execution
    """,
)
async def reconcile_storage(
    request: ReconcileRequest,
    db: AsyncSession = Depends(get_db),
) -> ReconcileResponse:
    """
    Reconcile BD ↔ Storage state.
    
    Protected by require_internal_service_token (APP_SERVICE_TOKEN).
    """
    try:
        service = ReconciliationService(db)
        response = await service.reconcile(request)
        return response
    
    except Exception as e:
        logger.exception(
            "reconcile_error",
            extra={"error": str(e)},
        )
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Reconciliation failed: {str(e)}",
        )


# Fin del archivo
