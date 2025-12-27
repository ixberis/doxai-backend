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
Actualizado: 2025-12-27 - Fix DI con PasswordHasher y SessionManager
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.shared.utils.http_exceptions import (
    NotFoundException,
    BadRequestException,
)
from app.shared.utils.security import hash_password, verify_password
from app.modules.user_profile.schemas import (
    UserProfileResponse,
    UserProfileUpdateRequest,
    UserProfileUpdateResponse,
    SubscriptionStatusResponse,
)
from app.modules.user_profile.services import ProfileService
from app.modules.auth.services import get_current_user

router = APIRouter(prefix="/profile", tags=["User Profile"])


# ---------------------------------------------------------------------------
# DI: Adaptadores para PasswordHasher y SessionManager
# ---------------------------------------------------------------------------

class PasswordHasherAdapter:
    """Adapter que implementa el protocolo PasswordHasher usando security utils."""
    
    def verify(self, plain_password: str, password_hash: str) -> bool:
        return verify_password(plain_password, password_hash)
    
    def hash(self, plain_password: str) -> str:
        return hash_password(plain_password)


class NoOpSessionManager:
    """
    SessionManager no-op para endpoints que no necesitan revocar sesiones.
    La revocación real de sesión se maneja en el módulo auth.
    """
    
    async def revoke_session(self, user_id: UUID, session_id: Optional[str]) -> None:
        # No-op: la revocación real ocurre en auth/logout
        pass


# Singletons para evitar recreación constante
_password_hasher = PasswordHasherAdapter()
_session_manager = NoOpSessionManager()


async def get_profile_service(
    db: AsyncSession = Depends(get_db),
) -> ProfileService:
    """
    Dependency provider para ProfileService.
    Inyecta db, password_hasher y session_manager correctamente.
    """
    return ProfileService(
        db=db,
        password_hasher=_password_hasher,
        session_manager=_session_manager,
    )


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


# ---------------------------------------------------------------------------
# Helper: Convertir ProfileDTO a UserProfileResponse
# ---------------------------------------------------------------------------
def _profile_dto_to_response(dto) -> dict:
    """
    Convierte ProfileDTO del servicio a formato compatible con UserProfileResponse.
    Los schemas esperan prefijo 'user_' en los campos.
    """
    from app.modules.auth.enums import UserRole, UserStatus
    
    # Parsear role con fallback a customer
    try:
        role = UserRole(dto.role) if dto.role else UserRole.customer
    except ValueError:
        role = UserRole.customer
    
    # Parsear status con fallback a active
    try:
        user_status = UserStatus(dto.status) if dto.status else UserStatus.active
    except ValueError:
        user_status = UserStatus.active
    
    return {
        "user_id": dto.user_id,
        "user_email": dto.email,
        "user_full_name": dto.full_name,
        "user_phone": dto.phone,
        "user_role": role,
        "user_status": user_status,
        "user_subscription_status": user_status,
        "subscription_period_end": None,  # No disponible en ProfileDTO
        "user_created_at": dto.created_at,
        "user_updated_at": dto.updated_at or dto.created_at,
        "user_last_login": dto.last_login,
    }


# ===== Profile Routes =====

@router.get(
    "",
    response_model=UserProfileResponse,
    summary="Obtener perfil de usuario",
    description="Obtiene el perfil completo del usuario autenticado"
)
async def get_user_profile(
    user=Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
):
    """
    Obtiene el perfil completo del usuario autenticado.
    """
    uid, _ = _uid_email(user)
    try:
        dto = await service.get_profile(user_id=uid)
        return _profile_dto_to_response(dto)
    except ValueError as e:
        raise NotFoundException(detail=str(e))
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
    service: ProfileService = Depends(get_profile_service),
):
    """Alias de get_user_profile para compatibilidad con UI."""
    uid, _ = _uid_email(user)
    try:
        dto = await service.get_profile(user_id=uid)
        return _profile_dto_to_response(dto)
    except ValueError as e:
        raise NotFoundException(detail=str(e))
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
    user=Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
):
    """
    Actualiza el perfil del usuario autenticado.
    """
    uid, _ = _uid_email(user)
    try:
        from datetime import datetime, timezone
        from app.modules.user_profile.services.profile_service import UpdateProfileDTO
        
        # Mapear campos del request (user_full_name -> full_name)
        dto = UpdateProfileDTO(
            full_name=profile_data.user_full_name,
            phone=profile_data.user_phone,
        )
        updated_dto = await service.update_profile(user_id=uid, data=dto)
        
        return {
            "success": True,
            "message": "Perfil actualizado correctamente",
            "updated_at": datetime.now(timezone.utc),
            "user": _profile_dto_to_response(updated_dto),
        }
    except ValueError as e:
        raise BadRequestException(detail=str(e))
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
    service: ProfileService = Depends(get_profile_service),
):
    """Alias de update_user_profile para compatibilidad con UI."""
    uid, _ = _uid_email(user)
    try:
        from datetime import datetime, timezone
        from app.modules.user_profile.services.profile_service import UpdateProfileDTO
        
        dto = UpdateProfileDTO(
            full_name=profile_data.user_full_name,
            phone=profile_data.user_phone,
        )
        updated_dto = await service.update_profile(user_id=uid, data=dto)
        
        return {
            "success": True,
            "message": "Perfil actualizado correctamente",
            "updated_at": datetime.now(timezone.utc),
            "user": _profile_dto_to_response(updated_dto),
        }
    except ValueError as e:
        raise BadRequestException(detail=str(e))
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
    user=Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
):
    """
    Obtiene el estado de suscripción del usuario autenticado.
    Usa créditos como proxy de suscripción.
    """
    from app.modules.auth.enums import UserStatus
    
    uid, _ = _uid_email(user)
    email = getattr(user, "email", None) or "unknown@example.com"
    
    try:
        balance = await service.get_credits_balance(user_id=uid)
        sub_status = UserStatus.active if balance > 0 else UserStatus.not_active
        
        return {
            "user_id": uid,
            "user_email": email,
            "subscription_status": sub_status,
            "subscription_period_start": None,
            "subscription_period_end": None,
            "last_payment_date": None,
        }
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
    db: AsyncSession = Depends(get_db),
):
    """
    Actualiza el timestamp de último login.
    Este endpoint usa SQL directo para evitar dependencias circulares.
    """
    uid, _ = _uid_email(user)
    try:
        from sqlalchemy import text
        from datetime import datetime, timezone
        
        await db.execute(
            text("UPDATE app_users SET user_last_login = :now WHERE user_id = :uid"),
            {"now": datetime.now(timezone.utc), "uid": str(uid)}
        )
        await db.commit()
    except Exception as e:
        raise BadRequestException(detail=f"Error al actualizar último login: {str(e)}")
