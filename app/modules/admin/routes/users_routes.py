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


# ─────────────────────────────────────────────────────────────────────────────
# Email Health Schemas
# ─────────────────────────────────────────────────────────────────────────────

class EmailStatusDetail(BaseModel):
    """Estado detallado de un tipo de correo."""
    status: str = Field(..., description="sent|pending|failed|n/a")
    sent_at: Optional[str] = None
    attempts: int = 0
    sent_count: int = Field(default=0, description="Total emails sent for this type")
    last_error: Optional[str] = None
    is_historical: bool = Field(default=False, description="True if this is historical data (user already completed this step)")


class EmailHealth(BaseModel):
    """Estado de salud de correos por usuario."""
    activation: EmailStatusDetail
    welcome: EmailStatusDetail
    overall: str = Field(..., description="ok|pending|failed")


class AdminUserResponse(BaseModel):
    """
    Canonical Admin User DTO.
    
    Contract:
    - user_id: always string (even if DB uses int), canonical ID for operations
    - user_id_type: "int" or "uuid" - for traceability/future migration
    - account_status: single source of truth for account state (active/suspended/etc)
    - activation_status: separate from account status (activated/pending)
    - deleted_at: soft-delete timestamp (null if active)
    - email_health: estado de correos de activación y bienvenida
    - phone: user phone number
    - last_login: last login timestamp
    """
    user_id: str                        # Canonical ID (string always)
    user_id_type: UserIdType = "int"    # Current backend uses int
    email: str
    full_name: Optional[str] = None
    phone: Optional[str] = None         # User phone number
    role: str = "customer"
    account_status: str = "active"      # Single source for Estado column
    activation_status: str = "pending"  # activated | pending
    created_at: str
    last_login: Optional[str] = None    # Last login timestamp
    deleted_at: Optional[str] = None    # Soft-delete timestamp
    email_health: Optional[EmailHealth] = None  # Estado de correos


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
    # Optional: update phone number
    phone: Optional[str] = Field(None, max_length=50)


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

# Whitelist for sortable columns
SORT_COLUMNS = {
    "email": "u.user_email",
    "name": "u.user_full_name",
    "role": "u.user_role",
    "status": "u.user_status",
    "activated": "u.user_is_activated",
    "created_at": "u.user_created_at",
}

VALID_ROLES = {"admin", "staff", "customer"}
VALID_STATUSES = {"active", "cancelled", "no_payment", "not_active", "suspended"}


@router.get("", response_model=AdminUsersListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    include_deleted: bool = Query(False),
    q: Optional[str] = Query(None, description="Búsqueda libre (email, nombre, rol, estado)"),
    role: Optional[str] = Query(None, description="Filtro por rol"),
    status: Optional[str] = Query(None, description="Filtro por estado"),
    activated: Optional[bool] = Query(None, description="Filtro por activado"),
    email_pending: Optional[bool] = Query(None, description="Filtro por correos pendientes"),
    sort_by: str = Query("created_at", description="Columna para ordenar"),
    sort_dir: str = Query("desc", description="Dirección: asc o desc"),
    db: AsyncSession = Depends(get_db),
):
    """
    List all users with pagination, search, filters, and sorting.
    Includes email_health for each user.
    """
    # Validate sort_by
    if sort_by not in SORT_COLUMNS:
        raise HTTPException(
            status_code=422,
            detail=f"sort_by inválido: '{sort_by}'. Valores permitidos: {list(SORT_COLUMNS.keys())}"
        )
    
    # Validate sort_dir
    if sort_dir.lower() not in ("asc", "desc"):
        raise HTTPException(
            status_code=422,
            detail=f"sort_dir inválido: '{sort_dir}'. Valores permitidos: asc, desc"
        )
    
    # Validate role filter
    if role and role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"role inválido: '{role}'")
    
    # Validate status filter
    if status and status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"status inválido: '{status}'")

    offset = (page - 1) * per_page
    sort_column = SORT_COLUMNS[sort_by]
    sort_direction = sort_dir.upper()

    # Build WHERE conditions
    conditions = []
    params: dict = {"limit": per_page, "offset": offset}
    
    if not include_deleted:
        conditions.append("u.deleted_at IS NULL")
    
    if role:
        conditions.append("u.user_role::text = :role")
        params["role"] = role
    
    if status:
        conditions.append("u.user_status::text = :status")
        params["status"] = status
    
    if activated is not None:
        conditions.append("u.user_is_activated = :activated")
        params["activated"] = activated
    
    # Filter for pending emails (server-side)
    if email_pending:
        conditions.append("""(
            -- Activation pending: user not activated and last activation has pending status
            (u.user_is_activated = false AND EXISTS (
                SELECT 1 FROM public.account_activations a
                WHERE a.user_id = u.user_id
                  AND a.activation_email_status IN ('pending', 'failed')
            ))
            OR
            -- Welcome pending: user activated but welcome not sent
            (u.user_is_activated = true AND u.welcome_email_status IN ('pending', 'failed'))
        )""")
    
    if q:
        q_lower = q.lower().strip()
        # Check if q matches a role or status value
        search_conditions = ["u.user_email ILIKE :q_like", "u.user_full_name ILIKE :q_like"]
        
        # Add role/status matching
        if q_lower in VALID_ROLES:
            search_conditions.append("u.user_role::text = :q_exact")
        if q_lower in VALID_STATUSES:
            search_conditions.append("u.user_status::text = :q_exact")
        
        conditions.append(f"({' OR '.join(search_conditions)})")
        params["q_like"] = f"%{q}%"
        params["q_exact"] = q_lower

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    
    # Log for debugging - verify no hidden activation filter
    logger.debug(
        "admin_users_query conditions=%s where_clause=%s params=%s include_deleted=%s email_pending=%s",
        conditions,
        where_clause,
        {k: v for k, v in params.items() if k not in ('limit', 'offset')},
        include_deleted,
        email_pending,
    )

    # Count total
    count_q = text(f"SELECT COUNT(*) FROM public.app_users u {where_clause}")
    count_res = await db.execute(count_q, params)
    total = count_res.scalar() or 0
    
    logger.info("admin_users_list total=%d page=%d include_deleted=%s", total, page, include_deleted)

    # Get users with email health data
    users_q = text(f"""
        SELECT 
            u.user_id::text AS user_id,
            u.user_email AS email,
            u.user_full_name AS full_name,
            u.user_phone AS phone,
            u.user_role::text AS role,
            u.user_status::text AS account_status,
            u.user_is_activated AS is_activated,
            u.user_created_at::text AS created_at,
            u.user_last_login::text AS last_login,
            u.deleted_at::text AS deleted_at,
            -- Welcome email fields
            u.welcome_email_status::text AS welcome_status,
            u.welcome_email_sent_at::text AS welcome_sent_at,
            u.welcome_email_attempts AS welcome_attempts,
            u.welcome_email_last_error AS welcome_last_error,
            -- For activated users: get last SENT activation email (with evidence)
            -- For non-activated users: get latest activation token (to detect pending/failed)
            (
                SELECT a.activation_email_status::text
                FROM public.account_activations a
                WHERE a.user_id = u.user_id
                  AND (
                    -- If user is activated, only consider tokens with evidence of sending
                    (u.user_is_activated = true AND (a.activation_email_sent_at IS NOT NULL OR a.activation_email_status = 'sent'))
                    OR
                    -- If user not activated, consider all tokens (need to detect pending/failed)
                    u.user_is_activated = false
                  )
                ORDER BY a.created_at DESC
                LIMIT 1
            ) AS activation_status_email,
            (
                SELECT a.activation_email_sent_at::text
                FROM public.account_activations a
                WHERE a.user_id = u.user_id
                  AND (
                    (u.user_is_activated = true AND (a.activation_email_sent_at IS NOT NULL OR a.activation_email_status = 'sent'))
                    OR
                    u.user_is_activated = false
                  )
                ORDER BY a.created_at DESC
                LIMIT 1
            ) AS activation_sent_at,
            -- For historical data where attempts wasn't tracked: GREATEST ensures minimum 1 when sent
            (
                SELECT GREATEST(
                    COALESCE(a.activation_email_attempts, 0),
                    CASE WHEN a.activation_email_sent_at IS NOT NULL OR a.activation_email_status = 'sent' THEN 1 ELSE 0 END
                )
                FROM public.account_activations a
                WHERE a.user_id = u.user_id
                  AND (
                    (u.user_is_activated = true AND (a.activation_email_sent_at IS NOT NULL OR a.activation_email_status = 'sent'))
                    OR
                    u.user_is_activated = false
                  )
                ORDER BY a.created_at DESC
                LIMIT 1
            ) AS activation_attempts,
            (
                SELECT a.activation_email_last_error
                FROM public.account_activations a
                WHERE a.user_id = u.user_id
                  AND (
                    (u.user_is_activated = true AND (a.activation_email_sent_at IS NOT NULL OR a.activation_email_status = 'sent'))
                    OR
                    u.user_is_activated = false
                  )
                ORDER BY a.created_at DESC
                LIMIT 1
            ) AS activation_last_error,
            -- Count of activation emails actually sent (for this user)
            (
                SELECT COUNT(*)
                FROM public.account_activations a
                WHERE a.user_id = u.user_id
                  AND a.activation_email_sent_at IS NOT NULL
            ) AS activation_emails_sent_count,
            -- Welcome emails sent count (currently 0 or 1)
            CASE WHEN u.welcome_email_sent_at IS NOT NULL THEN 1 ELSE 0 END AS welcome_emails_sent_count
        FROM public.app_users u
        {where_clause}
        ORDER BY {sort_column} {sort_direction}
        LIMIT :limit OFFSET :offset
    """)

    res = await db.execute(users_q, params)
    rows = res.fetchall()

    def build_email_health(row) -> EmailHealth:
        """Build email health object based on user's activation status."""
        is_activated = row.is_activated
        
        # Activation email status - show historical data for activated users
        if row.activation_status_email:
            # Has activation email data
            if is_activated:
                # User already activated - normalize status to 'sent' ONLY if there's real evidence
                # Evidence: sent_at exists OR status is explicitly 'sent'
                # NOTE: 'pending' is NOT evidence - it just means token was created, not that email was sent
                has_evidence = (row.activation_sent_at is not None) or (row.activation_status_email == "sent")
                if has_evidence:
                    activation_detail = EmailStatusDetail(
                        status="sent",
                        sent_at=row.activation_sent_at,
                        attempts=row.activation_attempts or 0,
                        sent_count=row.activation_emails_sent_count or 0,
                        last_error=row.activation_last_error,
                        is_historical=True,
                    )
                else:
                    # Activated but no evidence of email sent - mark as n/a (historical)
                    activation_detail = EmailStatusDetail(
                        status="n/a",
                        attempts=row.activation_attempts or 0,
                        sent_count=row.activation_emails_sent_count or 0,
                        is_historical=True,
                    )
            else:
                # User not activated - show latest activation email status
                activation_detail = EmailStatusDetail(
                    status=row.activation_status_email,
                    sent_at=row.activation_sent_at,
                    attempts=row.activation_attempts or 0,
                    sent_count=row.activation_emails_sent_count or 0,
                    last_error=row.activation_last_error,
                    is_historical=False,
                )
        elif is_activated:
            # User is activated but no activation email data - use n/a
            activation_detail = EmailStatusDetail(status="n/a", attempts=0, sent_count=row.activation_emails_sent_count or 0, is_historical=True)
        else:
            # User not activated and no activation email data
            activation_detail = EmailStatusDetail(status="n/a", attempts=0, sent_count=0, is_historical=False)
        
        # Welcome email status - only relevant for activated users
        if is_activated:
            welcome_detail = EmailStatusDetail(
                status=row.welcome_status or "pending",
                sent_at=row.welcome_sent_at,
                attempts=row.welcome_attempts or 0,
                sent_count=row.welcome_emails_sent_count or 0,
                last_error=row.welcome_last_error,
                is_historical=False,  # Welcome is current concern for activated users
            )
        else:
            welcome_detail = EmailStatusDetail(status="n/a", attempts=0, sent_count=0, is_historical=False)
        
        # Calculate overall status based on the relevant email for this user
        if not is_activated:
            # User not activated - check activation email
            if activation_detail.status == "sent":
                overall = "ok"
            elif activation_detail.status == "failed":
                overall = "failed"
            elif activation_detail.status == "n/a":
                overall = "pending"  # No activation email sent yet
            else:
                overall = "pending"
        else:
            # User activated - check welcome email only
            if welcome_detail.status == "sent":
                overall = "ok"
            elif welcome_detail.status == "failed":
                overall = "failed"
            else:
                overall = "pending"
        
        return EmailHealth(
            activation=activation_detail,
            welcome=welcome_detail,
            overall=overall,
        )

    import os
    log_admin_debug = os.getenv("LOG_ADMIN_USERS_DEBUG", "0") == "1"
    is_non_prod = os.getenv("ENVIRONMENT", "development") != "production"
    
    users = []
    for row in rows:
        # DEBUG: Log phone/last_login for first 3 users (only in non-prod or with explicit flag)
        # Phone is redacted to last 2 digits for privacy
        if len(users) < 3 and (log_admin_debug or is_non_prod):
            phone_redacted = f"***{row.phone[-2:]}" if row.phone and len(row.phone) >= 2 else "(empty)"
            logger.debug(
                "admin_user_sample user_id=%s phone=%s last_login=%r",
                row.user_id, phone_redacted, row.last_login
            )
        
        users.append(AdminUserResponse(
            user_id=row.user_id,
            user_id_type="int",
            email=row.email,
            full_name=row.full_name,
            phone=row.phone if row.phone else None,  # Normalize empty string to None
            role=row.role,
            account_status=row.account_status,
            activation_status="activated" if row.is_activated else "pending",
            created_at=row.created_at,
            last_login=row.last_login,
            deleted_at=row.deleted_at,
            email_health=build_email_health(row),
        ))

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

    # Update phone if provided
    if payload.phone is not None:
        update_phone_q = text("""
            UPDATE public.app_users 
            SET user_phone = :phone
            WHERE user_id = :uid
        """)
        await db.execute(update_phone_q, {"phone": payload.phone.strip() if payload.phone else None, "uid": resolved_id})
        logger.info(f"admin_user_phone_updated user_id={resolved_id}")

    await db.commit()

    # Fetch updated user with phone and last_login
    fetch_q = text("""
        SELECT 
            u.user_id::text AS user_id,
            u.user_email AS email,
            u.user_full_name AS full_name,
            u.user_phone AS phone,
            u.user_role::text AS role,
            u.user_status::text AS account_status,
            u.user_is_activated AS is_activated,
            u.user_created_at::text AS created_at,
            u.user_last_login::text AS last_login
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
        phone=row.phone if row.phone else None,
        role=row.role,
        account_status=row.account_status,
        activation_status="activated" if row.is_activated else "pending",
        created_at=row.created_at,
        last_login=row.last_login,
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


# ─────────────────────────────────────────────────────────────────────────────
# Restore User (Undelete)
# ─────────────────────────────────────────────────────────────────────────────

class RestoreUserResponse(BaseModel):
    ok: bool
    user_id: str
    deleted_at: None = None


@router.post("/{user_id}/restore", response_model=RestoreUserResponse)
async def restore_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Restore a soft-deleted user (sets deleted_at = NULL).
    Idempotent: if user is not deleted, returns success without changes.
    """
    resolved_id, id_type = resolve_user_id(user_id)
    logger.info(f"admin_user_restore_started user_id={resolved_id}")

    # Verify user exists
    check_q = text("""
        SELECT user_id, user_email, deleted_at 
        FROM public.app_users 
        WHERE user_id = :uid
    """)
    check_res = await db.execute(check_q, {"uid": resolved_id})
    user_row = check_res.first()
    
    if not user_row:
        logger.warning(f"admin_user_restore_failed user_id={resolved_id} reason=not_found")
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Idempotent: if not deleted, return success
    if user_row.deleted_at is None:
        logger.info(f"admin_user_restore_not_deleted user_id={resolved_id} email={user_row.user_email}")
        return RestoreUserResponse(ok=True, user_id=str(resolved_id))

    # Restore user
    try:
        restore_q = text("""
            UPDATE public.app_users 
            SET deleted_at = NULL,
                updated_at = NOW()
            WHERE user_id = :uid
        """)
        await db.execute(restore_q, {"uid": resolved_id})
        await db.commit()
        
        logger.info(f"admin_user_restore_success user_id={resolved_id} email={user_row.user_email}")
        
        return RestoreUserResponse(ok=True, user_id=str(resolved_id))
    except Exception as e:
        logger.exception(f"admin_user_restore_failed user_id={resolved_id} error={e}")
        raise HTTPException(status_code=500, detail="Error al restaurar usuario")


# Fin del archivo
