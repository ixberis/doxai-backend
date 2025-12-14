# -*- coding: utf-8 -*-
"""
backend/app/modules/user_profile/routes/profile_routes.py

Rutas consolidadas del módulo de perfil de usuario.

Este módulo expone endpoints autenticados para:
- Consultar perfil de usuario (GET /profile)
- Actualizar perfil (PUT /profile)
- Consultar estado de suscripción (GET /subscription)

⚠️ Todos los endpoints requieren autenticación JWT

Autor: DoxAI
Fecha: 2025-10-18
"""

from uuid import UUID
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

router = APIRouter(prefix="/profile", tags=["User Profile"])


# ===== Profile Routes =====

@router.get(
    "",
    response_model=UserProfileResponse,
    summary="Obtener perfil de usuario",
    description="Obtiene el perfil completo del usuario autenticado"
)
async def get_user_profile(
    user_id: UUID,  # TODO: Replace with get_current_user_id dependency
    db: Session = Depends(get_db),
):
    """
    Obtiene el perfil completo del usuario autenticado.
    
    Args:
        user_id: ID del usuario (extraído del token JWT)
        db: Sesión de base de datos
        
    Returns:
        Perfil completo del usuario
    """
    service = UserProfileService(db)
    try:
        return service.get_profile_by_id(user_id=user_id)
    except HTTPException:
        raise
    except Exception as e:
        raise BadRequestException(detail=f"Error al obtener perfil: {str(e)}")


@router.put(
    "",
    response_model=UserProfileUpdateResponse,
    summary="Actualizar perfil de usuario",
    description="Actualiza nombre y/o teléfono del usuario autenticado"
)
async def update_user_profile(
    profile_data: UserProfileUpdateRequest,
    user_id: UUID,  # TODO: Replace with get_current_user_id dependency
    db: Session = Depends(get_db),
):
    """
    Actualiza el perfil del usuario autenticado.
    
    Args:
        profile_data: Datos a actualizar (nombre, teléfono)
        user_id: ID del usuario (extraído del token JWT)
        db: Sesión de base de datos
        
    Returns:
        Respuesta con el perfil actualizado
    """
    service = UserProfileService(db)
    try:
        return service.update_profile(
            user_id=user_id,
            profile_data=profile_data
        )
    except HTTPException:
        raise
    except Exception as e:
        raise BadRequestException(detail=f"Error al actualizar perfil: {str(e)}")


# ===== Subscription Routes =====

@router.get(
    "/subscription",
    response_model=SubscriptionStatusResponse,
    summary="Obtener estado de suscripción",
    description="Obtiene el estado actual de la suscripción del usuario"
)
async def get_subscription_status(
    user_id: UUID,  # TODO: Replace with get_current_user_id dependency
    db: Session = Depends(get_db),
):
    """
    Obtiene el estado de suscripción del usuario autenticado.
    
    Args:
        user_id: ID del usuario (extraído del token JWT)
        db: Sesión de base de datos
        
    Returns:
        Estado de suscripción con fechas y último pago
    """
    service = UserProfileService(db)
    try:
        return service.get_subscription_status(user_id=user_id)
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
    user_id: UUID,  # TODO: Replace with get_current_user_id dependency
    db: Session = Depends(get_db),
):
    """
    Actualiza el timestamp de último login.
    
    Args:
        user_id: ID del usuario (extraído del token JWT)
        db: Sesión de base de datos
        
    Returns:
        204 No Content
    """
    service = UserProfileService(db)
    try:
        service.update_last_login(user_id=user_id)
    except Exception as e:
        raise BadRequestException(detail=f"Error al actualizar último login: {str(e)}")
