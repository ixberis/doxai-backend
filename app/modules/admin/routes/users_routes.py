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
    # Optional: update full_name
    full_name: Optional[str] = Field(None, max_length=255)


class DeleteUserResponse(BaseModel):
    success: bool
    message: str


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
    include_deleted: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """
    List all users with pagination.
    Returns user info including role (from user_roles) and activation status.
    Excludes soft-deleted users by default (deleted_at IS NOT NULL).
    """
    offset = (page - 1) * per_page

    # Count total (excluding deleted unless requested)
    deleted_filter = "" if include_deleted else "WHERE deleted_at IS NULL"
    count_q = text(f"SELECT COUNT(*) FROM public.app_users {deleted_filter}")
    count_res = await db.execute(count_q)
    total = count_res.scalar() or 0

    # Get users with role from app_users table and activation status
    # Note: app_users uses user_* column names and user_status enum
    deleted_where = "" if include_deleted else "WHERE u.deleted_at IS NULL"
    users_q = text(f"""
        SELECT 
            u.user_id::text AS user_id,
            u.user_email AS email,
            u.user_full_name AS full_name,
            u.user_role::text AS role,
            u.user_status::text AS account_status,
            u.user_is_activated AS is_activated,
            u.user_created_at::text AS created_at
        FROM public.app_users u
        {deleted_where}
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
            SET user_status = CAST(:status AS user_status_enum)
            WHERE user_id = :uid
        """)
        await db.execute(update_status_q, {"status": payload.status, "uid": resolved_id})
        logger.info(f"admin_user_status_updated user_id={resolved_id} new_status={payload.status}")

    # Update role if provided (using user_role enum in app_users)
    if payload.role is not None:
        update_role_q = text("""
            UPDATE public.app_users 
            SET user_role = CAST(:role AS user_role_enum)
            WHERE user_id = :uid
        """)
        try:
            await db.execute(update_role_q, {"role": payload.role, "uid": resolved_id})
            logger.info(f"admin_user_role_updated user_id={resolved_id} new_role={payload.role}")
        except Exception as e:
            logger.exception(f"Could not update role for {resolved_id}: {e}")
            raise HTTPException(status_code=500, detail="Error al actualizar rol")

    # Update full_name if provided
    if payload.full_name is not None:
        update_name_q = text("""
            UPDATE public.app_users 
            SET user_full_name = :name
            WHERE user_id = :uid
        """)
        await db.execute(update_name_q, {"name": payload.full_name, "uid": resolved_id})
        logger.info(f"admin_user_name_updated user_id={resolved_id}")

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


@router.delete("/{user_id}", response_model=DeleteUserResponse)
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_admin),
):
    """
    Soft delete a user (sets deleted_at timestamp).
    Cannot delete your own account.
    """
    resolved_id, id_type = resolve_user_id(user_id)
    logger.debug(f"DELETE user_id={user_id} -> {resolved_id} (type={id_type})")

    # Prevent self-deletion
    if hasattr(current_user, 'user_id') and current_user.user_id == resolved_id:
        raise HTTPException(
            status_code=409, 
            detail="No puedes eliminar tu propia cuenta"
        )

    # Verify user exists and not already deleted
    check_q = text("""
        SELECT user_id, user_email FROM public.app_users 
        WHERE user_id = :uid AND deleted_at IS NULL
    """)
    check_res = await db.execute(check_q, {"uid": resolved_id})
    user_row = check_res.first()
    
    if not user_row:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Soft delete
    delete_q = text("""
        UPDATE public.app_users 
        SET deleted_at = NOW()
        WHERE user_id = :uid
    """)
    await db.execute(delete_q, {"uid": resolved_id})
    await db.commit()
    
    logger.info(f"admin_user_deleted user_id={resolved_id} email={user_row.user_email}")

    return DeleteUserResponse(
        success=True,
        message=f"Usuario {user_row.user_email} eliminado"
    )


# Fin del archivo
