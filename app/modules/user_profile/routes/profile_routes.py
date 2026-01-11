# -*- coding: utf-8 -*-
"""
backend/app/modules/user_profile/routes/profile_routes.py

Rutas consolidadas del módulo de perfil de usuario.

Este módulo expone endpoints autenticados para:
- Consultar perfil de usuario (GET /profile y GET /profile/profile)
- Actualizar perfil (PUT /profile y PUT /profile/profile)
- Consultar estado de suscripción (GET /subscription)

⚠️ Todos los endpoints requieren autenticación JWT

Timing por fases:
- auth_context: extracción y validación de user_id/email
- db_query: consulta a base de datos
- service: lógica de negocio adicional
- serialization: transformación de DTOs a response

Autor: DoxAI
Fecha: 2025-10-18
Actualizado: 2025-01-07 - Timing por fases completo + error handling estándar
"""

from typing import Optional
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db, get_db_timed
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
# SSOT: get_current_user_ctx (Core) para rutas optimizadas, get_current_user (ORM) para retrocompatibilidad
from app.modules.auth.services import get_current_user, get_current_user_ctx
from app.modules.auth.schemas.auth_context_dto import AuthContextDTO
from app.shared.auth_context import extract_user_id, extract_auth_user_id

router = APIRouter(tags=["User Profile"])

logger = logging.getLogger(__name__)


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
    
    async def revoke_session(self, user_id: int, session_id: Optional[str]) -> None:
        # No-op: la revocación real ocurre en auth/logout
        pass


# Singletons para evitar recreación constante
_password_hasher = PasswordHasherAdapter()
_session_manager = NoOpSessionManager()


def get_profile_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ProfileService:
    """
    Dependency provider para ProfileService (rutas legacy).
    Inyecta db, password_hasher y session_manager correctamente.
    
    Timing: records dep_factory.profile_service_ms
    """
    from app.shared.observability.dep_timing import record_dep_timing
    
    start = time.perf_counter()
    svc = ProfileService(
        db=db,
        password_hasher=_password_hasher,
        session_manager=_session_manager,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    record_dep_timing(request, "dep_factory.profile_service_ms", elapsed_ms)
    return svc


def get_profile_service_timed(
    request: Request,
    db: AsyncSession = Depends(get_db_timed),
) -> ProfileService:
    """
    Dependency provider para ProfileService con get_db_timed.
    
    Rutas críticas (credits, subscription) usan esta versión para
    obtener instrumentación granular de DB (pool checkout, configure).
    
    Timing: records dep_factory.profile_service_ms
    """
    from app.shared.observability.dep_timing import record_dep_timing
    
    start = time.perf_counter()
    svc = ProfileService(
        db=db,
        password_hasher=_password_hasher,
        session_manager=_session_manager,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    record_dep_timing(request, "dep_factory.profile_service_ms", elapsed_ms)
    return svc


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
        "user_id": dto.user_id,  # int - schema actualizado para aceptar int
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


# ---------------------------------------------------------------------------
# Internal: Lógica compartida para GET profile (evita duplicación)
# ---------------------------------------------------------------------------
async def _get_profile_internal(
    user,
    service: ProfileService,
    endpoint_name: str = "get_profile",
) -> dict:
    """
    Lógica interna para obtener perfil con timing por fases.
    
    Fases medidas:
    - auth_context: extracción de user_id
    - db_query: tiempo de consulta a BD
    - serialization: tiempo de transformación DTO → response
    
    Returns:
        dict con datos del perfil listos para response
        
    Raises:
        NotFoundException: si el usuario no existe
        HTTPException(500): en errores internos
    """
    start_total = time.perf_counter()
    
    # Fase 1: Auth Context
    auth_start = time.perf_counter()
    uid = extract_user_id(user)
    auth_ms = (time.perf_counter() - auth_start) * 1000
    
    if auth_ms > 500:
        logger.warning(
            "query_slow op=%s phase=auth_context user_id=%s duration_ms=%.2f",
            endpoint_name, uid, auth_ms
        )
    
    try:
        # Fase 2: DB Query
        db_start = time.perf_counter()
        dto = await service.get_profile(user_id=uid)
        db_ms = (time.perf_counter() - db_start) * 1000
        
        if db_ms > 500:
            logger.warning(
                "query_slow op=%s phase=db_query user_id=%s duration_ms=%.2f",
                endpoint_name, uid, db_ms
            )
        
        # Fase 3: Serialization
        ser_start = time.perf_counter()
        response_data = _profile_dto_to_response(dto)
        ser_ms = (time.perf_counter() - ser_start) * 1000
        
        if ser_ms > 500:
            logger.warning(
                "query_slow op=%s phase=serialization user_id=%s duration_ms=%.2f",
                endpoint_name, uid, ser_ms
            )
        
        # Total
        total_ms = (time.perf_counter() - start_total) * 1000
        logger.info(
            "query_completed op=%s user_id=%s auth_ms=%.2f db_ms=%.2f ser_ms=%.2f total_ms=%.2f",
            endpoint_name, uid, auth_ms, db_ms, ser_ms, total_ms
        )
        
        return response_data
        
    except ValueError as e:
        total_ms = (time.perf_counter() - start_total) * 1000
        logger.warning(
            "query_not_found op=%s user_id=%s duration_ms=%.2f",
            endpoint_name, uid, total_ms
        )
        raise NotFoundException(detail=str(e))
    except Exception:
        total_ms = (time.perf_counter() - start_total) * 1000
        logger.exception(
            "query_error op=%s user_id=%s duration_ms=%.2f",
            endpoint_name, uid, total_ms
        )
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Error interno al obtener perfil",
                "error_code": "PROFILE_FETCH_ERROR",
            }
        )


async def _update_profile_internal(
    user,
    profile_data: UserProfileUpdateRequest,
    service: ProfileService,
    endpoint_name: str = "update_profile",
) -> dict:
    """
    Lógica interna para actualizar perfil con timing por fases.
    """
    from datetime import datetime, timezone
    from app.modules.user_profile.services.profile_service import UpdateProfileDTO
    
    start_total = time.perf_counter()
    
    # Fase 1: Auth Context
    auth_start = time.perf_counter()
    uid = extract_user_id(user)
    auth_ms = (time.perf_counter() - auth_start) * 1000
    
    try:
        # Fase 2: DB Update
        db_start = time.perf_counter()
        dto = UpdateProfileDTO(
            full_name=profile_data.user_full_name,
            phone=profile_data.user_phone,
        )
        updated_dto = await service.update_profile(user_id=uid, data=dto)
        db_ms = (time.perf_counter() - db_start) * 1000
        
        if db_ms > 500:
            logger.warning(
                "query_slow op=%s phase=db_update user_id=%s duration_ms=%.2f",
                endpoint_name, uid, db_ms
            )
        
        # Fase 3: Serialization
        ser_start = time.perf_counter()
        response_data = {
            "success": True,
            "message": "Perfil actualizado correctamente",
            "updated_at": datetime.now(timezone.utc),
            "user": _profile_dto_to_response(updated_dto),
        }
        ser_ms = (time.perf_counter() - ser_start) * 1000
        
        # Total
        total_ms = (time.perf_counter() - start_total) * 1000
        logger.info(
            "query_completed op=%s user_id=%s auth_ms=%.2f db_ms=%.2f ser_ms=%.2f total_ms=%.2f",
            endpoint_name, uid, auth_ms, db_ms, ser_ms, total_ms
        )
        
        return response_data
        
    except ValueError as e:
        raise BadRequestException(detail=str(e))
    except Exception:
        total_ms = (time.perf_counter() - start_total) * 1000
        logger.exception(
            "query_error op=%s user_id=%s duration_ms=%.2f",
            endpoint_name, uid, total_ms
        )
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Error interno al actualizar perfil",
                "error_code": "PROFILE_UPDATE_ERROR",
            }
        )


# ===== Profile Routes =====

@router.get(
    "/",
    response_model=UserProfileResponse,
    summary="Obtener perfil de usuario",
    description="Obtiene el perfil completo del usuario autenticado"
)
async def get_user_profile(
    user=Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
):
    """Obtiene el perfil completo del usuario autenticado."""
    return await _get_profile_internal(user, service, "get_profile")


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
    return await _get_profile_internal(user, service, "get_profile_alias")


@router.put(
    "/",
    response_model=UserProfileUpdateResponse,
    summary="Actualizar perfil de usuario",
    description="Actualiza nombre y/o teléfono del usuario autenticado"
)
async def update_user_profile(
    profile_data: UserProfileUpdateRequest,
    user=Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
):
    """Actualiza el perfil del usuario autenticado."""
    return await _update_profile_internal(user, profile_data, service, "update_profile")


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
    return await _update_profile_internal(user, profile_data, service, "update_profile_alias")


# ===== Credits Routes =====

@router.get(
    "/credits",
    summary="Obtener balance de créditos",
    description="Obtiene el balance actual de créditos del usuario"
)
async def get_credits_balance(
    request: Request,
    ctx: AuthContextDTO = Depends(get_current_user_ctx),  # Core mode (~40ms vs ~1200ms ORM)
    service: ProfileService = Depends(get_profile_service_timed),  # DB instrumentation
):
    """
    Obtiene el balance de créditos del usuario autenticado.
    
    BD 2.0 SSOT: Usa auth_user_id (UUID) para consultar wallets.
    OPTIMIZADO: Usa get_current_user_ctx (Core) en lugar de get_current_user (ORM).
    
    Errores: Retorna HTTP 500 con error_code estándar (NO oculta errores).
    """
    from app.shared.observability.request_telemetry import RequestTelemetry
    
    telemetry = RequestTelemetry.create("profile.credits")
    
    # Variables para safe access en except blocks
    uid = None
    auth_uid = None
    
    try:
        # BD 2.0 SSOT: auth_user_id ya resuelto por get_current_user_ctx (Core)
        uid = ctx.user_id
        auth_uid = ctx.auth_user_id
        
        # Fase: DB Query (BD 2.0: usa auth_user_id para wallets)
        with telemetry.measure("db_ms"):
            balance = await service.get_credits_balance(user_id=uid, auth_user_id=auth_uid)
        
        # Fase: Serialization (minimal for this route)
        with telemetry.measure("ser_ms"):
            response = {"credits_balance": balance}
        
        # Set flags for observability (no PII)
        telemetry.set_flag("auth_user_id", f"{str(auth_uid)[:8]}...")
        telemetry.set_flag("balance", balance)
        
        telemetry.finalize(request, status_code=200, result="success")
        
        return response
        
    except HTTPException as e:
        telemetry.set_flag("auth_user_id", f"{str(auth_uid)[:8]}..." if auth_uid else "unknown")
        telemetry.finalize(request, status_code=e.status_code, result="http_error")
        raise
    except Exception as e:
        telemetry.set_flag("auth_user_id", f"{str(auth_uid)[:8]}..." if auth_uid else "unknown")
        telemetry.finalize(request, status_code=500, result="error")
        logger.exception(
            "query_error op=get_credits auth_user_id=%s error=%s",
            f"{str(auth_uid)[:8]}..." if auth_uid else "unknown", str(e)
        )
        # NO ocultar errores - devolver 500 con código de error estándar
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Error interno al obtener créditos",
                "error_code": "CREDITS_FETCH_ERROR",
            }
        )


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
    BD 2.0 SSOT: Usa auth_user_id (UUID) para consultar wallets.
    """
    from app.modules.auth.enums import UserStatus
    
    start_total = time.perf_counter()
    
    # Fase 1: Auth Context - extraer user_id (int) y auth_user_id (UUID SSOT)
    auth_start = time.perf_counter()
    uid = extract_user_id(user)
    auth_uid = extract_auth_user_id(user)  # BD 2.0 SSOT
    email = getattr(user, "user_email", None) or getattr(user, "email", None) or "unknown@example.com"
    auth_ms = (time.perf_counter() - auth_start) * 1000
    
    try:
        # Fase 2: DB Query (BD 2.0: usa auth_user_id para wallets)
        db_start = time.perf_counter()
        balance = await service.get_credits_balance(user_id=uid, auth_user_id=auth_uid)
        db_ms = (time.perf_counter() - db_start) * 1000
        
        sub_status = UserStatus.active if balance > 0 else UserStatus.not_active
        
        total_ms = (time.perf_counter() - start_total) * 1000
        logger.info(
            "query_completed op=get_subscription auth_user_id=%s balance=%s auth_ms=%.2f db_ms=%.2f total_ms=%.2f",
            str(auth_uid)[:8] + "...", balance, auth_ms, db_ms, total_ms
        )
        
        return {
            "user_id": uid,  # int - schema espera int
            "user_email": email,
            "subscription_status": sub_status,
            "subscription_period_start": None,
            "subscription_period_end": None,
            "last_payment_date": None,
        }
    except Exception:
        total_ms = (time.perf_counter() - start_total) * 1000
        logger.exception(
            "query_error op=get_subscription auth_user_id=%s duration_ms=%.2f",
            str(auth_uid)[:8] + "..." if auth_uid else "unknown", total_ms
        )
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Error interno al obtener estado de suscripción",
                "error_code": "SUBSCRIPTION_FETCH_ERROR",
            }
        )


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
    uid = extract_user_id(user)
    try:
        from sqlalchemy import text
        from datetime import datetime, timezone
        
        await db.execute(
            text("UPDATE app_users SET user_last_login = :now WHERE user_id = :uid"),
            {"now": datetime.now(timezone.utc), "uid": uid}  # uid is int, not str
        )
        await db.commit()
    except Exception:
        logger.exception("Error al actualizar último login para user_id=%s", uid)
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Error interno al actualizar último login",
                "error_code": "LAST_LOGIN_UPDATE_ERROR",
            }
        )
