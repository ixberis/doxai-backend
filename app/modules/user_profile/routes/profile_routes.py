# -*- coding: utf-8 -*-
"""
backend/app/modules/user_profile/routes/profile_routes.py

Rutas consolidadas del módulo de perfil de usuario.

Este módulo expone endpoints autenticados para:
- Consultar perfil de usuario (GET /profile y GET /profile/profile)
- Actualizar perfil (PUT /profile y PUT /profile/profile)
- Consultar estado de suscripción (GET /subscription)

⚠️ Todos los endpoints requieren autenticación JWT

Autor: DoxAI
Fecha: 2025-10-18
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.shared.database import get_db
from app.shared.utils.http_exceptions import (
    NotFoundException,
    BadRequestException,
)
from app.modules.user_profile.schemas import (
    UserProfileResponse,
    UserProfileUpdateRequest,
    UserProfileUpdateResponse,
    SubscriptionStatusResponse,
)
from app.modules.user_profile.services import UserProfileService
from app.modules.auth.services import get_current_user

router = APIRouter(prefix="/profile", tags=["User Profile"])


# ---------------------------------------------------------------------------
# Helper universal para user_id/email (copiado del patrón de projects)
# ---------------------------------------------------------------------------
def _uid_email(u):
    """Extrae user_id y email del objeto usuario (acepta objeto o dict)."""
    user_id = getattr(u, "user_id", None) or getattr(u, "id", None)
    email = getattr(u, "email", None)
    if user_id is None and isinstance(u, dict):
        user_id = u.get("user_id") or u.get("id")
        email = email or u.get("email")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth context")
    return user_id, email


# ===== Profile Routes =====

@router.get(
    "",
    response_model=UserProfileResponse,
    summary="Obtener perfil de usuario",
    description="Obtiene el perfil completo del usuario autenticado"
)
async def get_user_profile(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Obtiene el perfil completo del usuario autenticado.
    """
    uid, _ = _uid_email(user)
    service = UserProfileService(db)
    try:
        return service.get_profile_by_id(user_id=uid)
    except HTTPException:
        raise
    except Exception as e:
        raise BadRequestException(detail=f"Error al obtener perfil: {str(e)}")


# Alias para compatibilidad con UI que llama GET /api/profile/profile
@router.get(
    "/profile",
    response_model=UserProfileResponse,
    summary="Obtener perfil de usuario (alias)",
    description="Alias de GET /profile para compatibilidad con UI"
)
async def get_user_profile_alias(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Alias de get_user_profile para compatibilidad con UI."""
    return await get_user_profile(user=user, db=db)


@router.put(
    "",
    response_model=UserProfileUpdateResponse,
    summary="Actualizar perfil de usuario",
    description="Actualiza nombre y/o teléfono del usuario autenticado"
)
async def update_user_profile(
    profile_data: UserProfileUpdateRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Actualiza el perfil del usuario autenticado.
    """
    uid, _ = _uid_email(user)
    service = UserProfileService(db)
    try:
        return service.update_profile(
            user_id=uid,
            profile_data=profile_data
        )
    except HTTPException:
        raise
    except Exception as e:
        raise BadRequestException(detail=f"Error al actualizar perfil: {str(e)}")


# Alias para compatibilidad con UI que llama PUT /api/profile/profile
@router.put(
    "/profile",
    response_model=UserProfileUpdateResponse,
    summary="Actualizar perfil de usuario (alias)",
    description="Alias de PUT /profile para compatibilidad con UI"
)
async def update_user_profile_alias(
    profile_data: UserProfileUpdateRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Alias de update_user_profile para compatibilidad con UI."""
    return await update_user_profile(profile_data=profile_data, user=user, db=db)


# ===== Subscription Routes =====

@router.get(
    "/subscription",
    response_model=SubscriptionStatusResponse,
    summary="Obtener estado de suscripción",
    description="Obtiene el estado actual de la suscripción del usuario"
)
async def get_subscription_status(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Obtiene el estado de suscripción del usuario autenticado.
    """
    uid, _ = _uid_email(user)
    service = UserProfileService(db)
    try:
        return service.get_subscription_status(user_id=uid)
    except HTTPException:
        raise
    except Exception as e:
        raise BadRequestException(detail=f"Error al obtener estado de suscripción: {str(e)}")


# ===== Utility Routes =====

@router.post(
    "/update-last-login",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Actualizar último login",
    description="Actualiza el timestamp de último acceso del usuario (llamado automáticamente en login)"
)
async def update_last_login(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Actualiza el timestamp de último login.
    """
    uid, _ = _uid_email(user)
    service = UserProfileService(db)
    try:
        service.update_last_login(user_id=uid)
    except Exception as e:
        raise BadRequestException(detail=f"Error al actualizar último login: {str(e)}")
