# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/routes/internal.py

Internal diagnostic endpoints for Projects module.
Protected by require_admin_strict (JWT-based admin auth).

Created: 2026-01-28
Author: Ixchel Beristain
"""

import logging
from uuid import UUID
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.shared.database.database import get_db
from app.modules.auth.dependencies import require_admin_strict
from app.modules.projects.models.project_models import Project

logger = logging.getLogger(__name__)


class SlugCheckResponse(BaseModel):
    """Response for slug-check diagnostic endpoint."""
    found: bool = Field(..., description="Whether a project with this slug exists for the user")
    project_id: Optional[UUID] = Field(None, description="Project ID if found")
    status: Optional[str] = Field(None, description="Project status (in_process, closed, etc.)")
    project_state: Optional[str] = Field(None, description="Project operational state")
    created_at: Optional[datetime] = Field(None, description="Project creation timestamp")
    closed_at: Optional[datetime] = Field(None, description="Project closure timestamp (retention anchor)")
    retention_grace_at: Optional[datetime] = Field(None, description="Retention grace period start")
    deleted_by_policy_at: Optional[datetime] = Field(None, description="Policy deletion timestamp")


# Router with require_admin_strict at router level (canonical pattern)
# Namespace: /_internal/projects/ for project-specific internal endpoints
router = APIRouter(
    prefix="/_internal/projects",
    tags=["projects:internal"],
    dependencies=[Depends(require_admin_strict)],
)


@router.get(
    "/slug-check",
    response_model=SlugCheckResponse,
    summary="Check if slug exists for user (diagnostic)",
    description="""
    Internal diagnostic endpoint for support to check 409 PROJECT_SLUG_ALREADY_EXISTS errors.
    
    **Requires admin authentication (require_admin_strict).**
    
    Returns project metadata if slug exists for the specified auth_user_id:
    - project_id, status, project_state, timestamps
    - Useful for diagnosing why a user can't create a project with a specific name
    
    **Security**: Only returns data for the specified auth_user_id, not cross-user data.
    """,
)
async def check_slug_exists(
    auth_user_id: UUID = Query(..., description="User's auth_user_id (UUID)"),
    slug: str = Query(..., min_length=1, description="Project slug to check"),
    db: AsyncSession = Depends(get_db),
) -> SlugCheckResponse:
    """
    Check if a project with the given slug exists for the specified user.
    
    This is an internal diagnostic endpoint for support to investigate
    409 PROJECT_SLUG_ALREADY_EXISTS errors.
    
    Security: Protected by require_admin_strict at router level.
    """
    # Query for the project with matching (auth_user_id, project_slug)
    stmt = select(Project).where(
        Project.auth_user_id == auth_user_id,
        Project.project_slug == slug,
    )
    
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    
    if not project:
        logger.info(
            "slug_check_not_found auth_user_id=%s slug=%s",
            str(auth_user_id)[:8],
            slug,
        )
        return SlugCheckResponse(found=False)
    
    logger.info(
        "slug_check_found auth_user_id=%s slug=%s project_id=%s status=%s",
        str(auth_user_id)[:8],
        slug,
        str(project.id)[:8],
        project.status.value if project.status else "unknown",
    )
    
    return SlugCheckResponse(
        found=True,
        project_id=project.id,
        status=project.status.value if project.status else None,
        project_state=project.state.value if project.state else None,
        created_at=project.created_at,
        closed_at=project.closed_at,
        retention_grace_at=getattr(project, 'retention_grace_at', None),
        deleted_by_policy_at=getattr(project, 'deleted_by_policy_at', None),
    )


# Fin del archivo backend/app/modules/projects/routes/internal.py
