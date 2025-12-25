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
from typing import Optional, Union
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
# Schemas - Canonical contract for Admin Users
# ─────────────────────────────────────────────────────────────────────────────

from typing import Literal

# Canonical ID type - currently int, exposed as string for frontend consistency
UserIdType = Literal["int", "uuid"]

class AdminUserResponse(BaseModel):
    """
    Canonical Admin User DTO.
    
    Contract:
    - user_id: always string (even if DB uses int), canonical ID for operations
    - user_id_type: "int" or "uuid" - for traceability/future migration
    - account_status: single source of truth for account state (active/suspended/etc)
    - activation_status: separate from account status (activated/pending)
    """
    user_id: str                        # Canonical ID (string always)
    user_id_type: UserIdType = "int"    # Current backend uses int
    email: str
    full_name: Optional[str] = None
    role: str = "customer"
    account_status: str = "active"      # Single source for Estado column
    activation_status: str = "pending"  # activated | pending
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
# ID Resolution - supports both int and UUID
# ─────────────────────────────────────────────────────────────────────────────

def resolve_user_id(user_id: str) -> tuple[Union[int, UUID], UserIdType]:
    """
    Resolve canonical user_id string to appropriate type.
    
    Returns:
        tuple: (resolved_id_for_query, id_type)
        - For int IDs: returns (int, "int")
        - For UUID IDs: returns (UUID, "uuid")
        
    Current backend uses int IDs, but this supports future UUID migration.
    """
    # If all digits, treat as int
    if user_id.isdigit():
        return int(user_id), "int"
    
    # Try to parse as UUID
    try:
        parsed_uuid = UUID(user_id)
        return parsed_uuid, "uuid"
    except ValueError:
        pass
    
    # Invalid format
    raise HTTPException(
        status_code=400, 
        detail=f"ID inválido: '{user_id}'. Debe ser numérico o UUID válido."
    )


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
            u.user_status::text AS account_status,
            u.user_is_activated AS is_activated,
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
            user_id_type="int",  # Current backend uses int IDs
            email=row.email,
            full_name=row.full_name,
            role=row.role,
            account_status=row.account_status,
            activation_status="activated" if row.is_activated else "pending",
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
    user_id: str,
    payload: UpdateUserRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Update user role or status.
    Accepts canonical user_id as string (int or UUID).
    - role: updates app_users.user_role
    - status: updates app_users.user_status
    """
    # Resolve canonical ID
    resolved_id, id_type = resolve_user_id(user_id)
    logger.debug(f"Resolving user_id={user_id} -> {resolved_id} (type={id_type})")

    # Verify user exists (current schema uses int)
    check_q = text("SELECT user_id FROM public.app_users WHERE user_id = :uid")
    check_res = await db.execute(check_q, {"uid": resolved_id})
    if not check_res.first():
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Update status if provided (using user_status enum)
    if payload.status is not None:
        update_status_q = text("""
            UPDATE public.app_users 
            SET user_status = :status::user_status_enum 
            WHERE user_id = :uid
        """)
        await db.execute(update_status_q, {"status": payload.status, "uid": resolved_id})

    # Update role if provided (using user_role enum in app_users)
    if payload.role is not None:
        update_role_q = text("""
            UPDATE public.app_users 
            SET user_role = :role::user_role_enum 
            WHERE user_id = :uid
        """)
        try:
            await db.execute(update_role_q, {"role": payload.role, "uid": resolved_id})
        except Exception as e:
            logger.exception(f"Could not update role for {resolved_id}: {e}")
            raise HTTPException(status_code=500, detail="Error al actualizar rol")

    await db.commit()

    # Fetch updated user
    fetch_q = text("""
        SELECT 
            u.user_id::text AS user_id,
            u.user_email AS email,
            u.user_full_name AS full_name,
            u.user_role::text AS role,
            u.user_status::text AS account_status,
            u.user_is_activated AS is_activated,
            u.user_created_at::text AS created_at
        FROM public.app_users u
        WHERE u.user_id = :uid
    """)
    res = await db.execute(fetch_q, {"uid": resolved_id})
    row = res.first()

    if not row:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    return AdminUserResponse(
        user_id=row.user_id,
        user_id_type=id_type,
        email=row.email,
        full_name=row.full_name,
        role=row.role,
        account_status=row.account_status,
        activation_status="activated" if row.is_activated else "pending",
        created_at=row.created_at,
    )


# Fin del archivo


# Fin del archivo
