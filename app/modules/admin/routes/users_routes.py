# -*- coding: utf-8 -*-
"""
backend/app/modules/admin/routes/users_routes.py

Admin endpoints for user management.
Requires admin role to access.

Autor: System
Fecha: 2025-12-21
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.modules.auth.dependencies import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/_internal/admin/users",
    tags=["admin-users"],
    dependencies=[Depends(require_admin)],
)


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class AdminUserResponse(BaseModel):
    user_id: str
    email: str
    full_name: Optional[str] = None
    role: str = "customer"  # Default role per user_role_enum
    status: str = "active"
    activated: bool = False
    created_at: str


class AdminUsersListResponse(BaseModel):
    users: list[AdminUserResponse]
    total: int
    page: int
    per_page: int


class UpdateUserRequest(BaseModel):
    # Aligned with user_role_enum: 'customer', 'admin', 'staff'
    role: Optional[str] = Field(None, pattern="^(admin|staff|customer)$")
    # Aligned with user_status_enum: 'active', 'cancelled', 'no_payment', 'not_active', 'suspended'
    status: Optional[str] = Field(None, pattern="^(active|cancelled|no_payment|not_active|suspended)$")


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=AdminUsersListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    List all users with pagination.
    Returns user info including role (from user_roles) and activation status.
    """
    offset = (page - 1) * per_page

    # Count total
    count_q = text("SELECT COUNT(*) FROM public.app_users")
    count_res = await db.execute(count_q)
    total = count_res.scalar() or 0

    # Get users with role from app_users table and activation status
    # Note: app_users uses user_* column names and user_status enum
    users_q = text("""
        SELECT 
            u.user_id::text AS user_id,
            u.user_email AS email,
            u.user_full_name AS full_name,
            u.user_role::text AS role,
            u.user_status::text AS status,
            u.user_is_activated AS activated,
            u.user_created_at::text AS created_at
        FROM public.app_users u
        ORDER BY u.user_created_at DESC
        LIMIT :limit OFFSET :offset
    """)

    res = await db.execute(users_q, {"limit": per_page, "offset": offset})
    rows = res.fetchall()

    users = [
        AdminUserResponse(
            user_id=row.user_id,
            email=row.email,
            full_name=row.full_name,
            role=row.role,
            status=row.status,
            activated=row.activated,
            created_at=row.created_at,
        )
        for row in rows
    ]

    return AdminUsersListResponse(
        users=users,
        total=total,
        page=page,
        per_page=per_page,
    )


@router.patch("/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: UUID,
    payload: UpdateUserRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Update user role or status.
    - role: updates user_roles table
    - status: updates app_users.is_active
    """
    user_id_str = str(user_id)

    # Verify user exists
    check_q = text("SELECT user_id FROM public.app_users WHERE user_id = :uid")
    check_res = await db.execute(check_q, {"uid": user_id_str})
    if not check_res.first():
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Update status if provided (using user_status enum)
    if payload.status is not None:
        update_status_q = text("""
            UPDATE public.app_users 
            SET user_status = :status::user_status_enum 
            WHERE user_id = :uid
        """)
        await db.execute(update_status_q, {"status": payload.status, "uid": user_id_str})

    # Update role if provided (using user_role enum in app_users)
    if payload.role is not None:
        update_role_q = text("""
            UPDATE public.app_users 
            SET user_role = :role::user_role_enum 
            WHERE user_id = :uid
        """)
        try:
            await db.execute(update_role_q, {"role": payload.role, "uid": user_id_str})
        except Exception as e:
            logger.exception(f"Could not update role for {user_id_str}: {e}")
            raise HTTPException(status_code=500, detail="Error al actualizar rol")

    await db.commit()

    # Fetch updated user
    fetch_q = text("""
        SELECT 
            u.user_id::text AS user_id,
            u.user_email AS email,
            u.user_full_name AS full_name,
            u.user_role::text AS role,
            u.user_status::text AS status,
            u.user_is_activated AS activated,
            u.user_created_at::text AS created_at
        FROM public.app_users u
        WHERE u.user_id = :uid
    """)
    res = await db.execute(fetch_q, {"uid": user_id_str})
    row = res.first()

    if not row:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    return AdminUserResponse(
        user_id=row.user_id,
        email=row.email,
        full_name=row.full_name,
        role=row.role,
        status=row.status,
        activated=row.activated,
        created_at=row.created_at,
    )


# Fin del archivo
