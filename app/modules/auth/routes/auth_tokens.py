# backend/app/modules/auth/routes/auth_tokens.py
# -*- coding: utf-8 -*-
"""
Rutas relacionadas con tokens / sesión de usuario:
- Login
- Refresh
- Logout (con revocación de sesión)
- Perfil (/me)

Autor: DoxAI / Refactor Fase 3
Fecha: 20/11/2025
Updated: 28/12/2025 - Session revocation on logout
"""

# Note: NOT using 'from __future__ import annotations' to ensure FastAPI
# can properly resolve Request type annotation for dependency injection

from fastapi import APIRouter, Depends, status, HTTPException, Request

from app.modules.auth.facades import get_auth_facade, AuthFacade
from app.modules.auth.schemas import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    TokenResponse,
    MessageResponse,
    UserOut,
)
from app.modules.auth.services.user_service import get_current_user_from_token
from app.modules.auth.services.session_service import SessionService
from app.modules.auth.models.user_models import AppUser
from app.shared.utils.jwt_utils import verify_token_type
from app.modules.auth.services.audit_service import AuditService
from app.shared.security.rate_limit_dep import RateLimitDep
from app.shared.http_utils.request_meta import get_request_meta
from app.shared.database.database import get_async_session
from app.shared.observability.timed_route import TimedAPIRoute
from sqlalchemy.ext.asyncio import AsyncSession

# Tag único para identificación en montaje (Swagger agrupa bajo "auth")
# route_class=TimedAPIRoute instruments all routes for handler timing
router = APIRouter(prefix="/auth", tags=["auth-tokens"], route_class=TimedAPIRoute)


# ------------------------ LOGIN ------------------------ #


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Login de usuario",
    dependencies=[Depends(RateLimitDep(endpoint="auth:login", key_type="ip"))],
)
async def login(
    payload: LoginRequest,
    request: Request,
    facade: AuthFacade = Depends(get_auth_facade),
):
    """
    Autentica al usuario con email y contraseña.

    Rate limiting:
      - 20 requests por IP cada 5 min
      - 5 intentos fallidos por email en 15 min → lockout 30 min

    El flujo interno:
      - Aplica rate limiting (LoginAttemptService).
      - Verifica credenciales.
      - Verifica que la cuenta esté activada.
      - Emite tokens de acceso y refresh.
      - Aplica backoff progresivo en intentos fallidos.
    """
    # Inject request metadata for audit trail
    meta = get_request_meta(request)
    data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
    data.update(meta)
    
    # Pass request as separate parameter (not in payload to avoid serialization leaks)
    return await facade.login(data, request=request)


# --------------------- REFRESH TOKEN --------------------- #


@router.post(
    "/token/refresh",
    response_model=TokenResponse,
    summary="Refrescar tokens de autenticación",
)
async def refresh_token(
    payload: RefreshRequest,
    facade: AuthFacade = Depends(get_auth_facade),
):
    """
    Refresca los tokens de autenticación a partir de un refresh_token válido.
    """
    return await facade.refresh_token(payload)


# -------------------------- LOGOUT -------------------------- #


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Logout (revoca sesión en servidor)",
)
async def logout(
    payload: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
) -> MessageResponse:
    """
    Logout con revocación de sesión:
      - Valida el refresh_token (tipo 'refresh').
      - Revoca todas las sesiones activas del usuario en user_sessions.
      - Esto hace que Auth Metrics refleje correctamente las sesiones activas.

    Si el refresh_token es inválido o expirado, responde 401.
    """
    if not payload.refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh token requerido.",
        )

    token_payload = verify_token_type(payload.refresh_token, expected_type="refresh")
    if not token_payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido o expirado.",
        )

    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sin identificador de usuario.",
        )

    # Revocar todas las sesiones del usuario
    session_service = SessionService(db)
    revoked_count = await session_service.revoke_all_sessions_for_user(int(user_id))

    # Auditoría: logout exitoso
    AuditService.log_logout(user_id=str(user_id))

    return MessageResponse(message=f"Logout exitoso. {revoked_count} sesión(es) revocada(s).")


# ------------------------ PERFIL /me ------------------------ #


@router.get(
    "/me",
    response_model=UserOut,
    summary="Perfil del usuario autenticado",
)
async def me(
    current_user: AppUser = Depends(get_current_user_from_token),
) -> UserOut:
    """
    Devuelve el perfil del usuario autenticado, tomando el user_id desde el
    access_token (JWT) vía get_current_user_from_token.

    Ya no requiere user_id por query.
    """
    return UserOut(
        user_id=current_user.user_id,
        user_email=current_user.user_email,
        user_full_name=current_user.user_full_name,
        user_role=current_user.user_role,
        user_status=current_user.user_status,
        user_phone=getattr(current_user, "user_phone", None),
        user_is_activated=getattr(current_user, "user_is_activated", None),
        user_created_at=getattr(current_user, "user_created_at", None),
    )


# Fin del archivo backend/app/modules/auth/routes/auth_tokens.py
