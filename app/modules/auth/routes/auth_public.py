# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/routes/auth_public.py

Rutas públicas de autenticación:
- Registro de usuario
- Activación de cuenta
- Reenvío de activación
- Inicio y confirmación de restablecimiento de contraseña

Estas rutas usan AuthFacade, que a su vez orquesta AuthService y los
flow services del módulo Auth (registro, activación, reset).

Autor: Ixchel Beristain
Fecha: 19/11/2025
Updated: 18/12/2025 - Added rate limiting
"""

# Note: NOT using 'from __future__ import annotations' to ensure FastAPI
# can properly resolve Request type annotation for dependency injection

from fastapi import APIRouter, Depends, Request, status

from app.modules.auth.facades import get_auth_facade, AuthFacade
from app.modules.auth.schemas import (
    RegisterRequest,
    RegisterResponse,
    ActivationRequest,
    ResendActivationRequest,
    PasswordResetRequest,
    PasswordResetConfirmRequest,
    MessageResponse,
)
from app.shared.http_utils.request_meta import get_request_meta
from app.shared.security.rate_limit_dep import RateLimitDep

# Tag único para identificación en montaje (Swagger agrupa bajo "auth")
router = APIRouter(prefix="/auth", tags=["auth-public"])


@router.post(
    "/register",
    response_model=None,  # Respuesta dinámica según resultado
    status_code=status.HTTP_201_CREATED,
    summary="Registro de usuario",
    dependencies=[Depends(RateLimitDep(endpoint="auth:register", key_type="ip"))],
)
async def register(
    payload: RegisterRequest,
    request: Request,
    facade: AuthFacade = Depends(get_auth_facade),
):
    """
    Registra un nuevo usuario en la plataforma.

    Flujo:
      1. Rate limiting por IP (3 requests / 10 min).
      2. Verificación de reCAPTCHA (si está habilitado en settings).
      3. Validación de unicidad de correo.
      4. Creación del usuario.
      5. Emisión de token de activación.
      6. Envío de correo de activación.
    
    ANTI-ENUMERACIÓN ESTRICTA:
      - Siempre responde 201 Created (para no filtrar existencia por status code)
      - Email nuevo: payload incluye user_id y access_token
      - Email existente: payload solo incluye message genérico
    """
    from app.shared.utils.json_response import UTF8JSONResponse
    import logging
    logger = logging.getLogger(__name__)
    
    # Inyectar metadatos de request para auditoría
    meta = get_request_meta(request)
    data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
    
    # DEBUG: Log phone field at route level (no PII)
    phone_value = data.get("phone")
    logger.info(
        "REGISTER_ROUTE: has_phone=%s phone_len=%d data_keys=%s",
        phone_value is not None and phone_value != "",
        len(phone_value) if phone_value else 0,
        list(data.keys()),
    )
    
    data.update(meta)
    
    result = await facade.register_user(data)
    
    # ANTI-ENUMERACIÓN: siempre 201 para no filtrar existencia por status code
    # El payload difiere (con/sin user_id) pero el status code es uniforme
    return UTF8JSONResponse(content=result, status_code=status.HTTP_201_CREATED)


@router.post(
    "/activation",
    response_model=MessageResponse,
    summary="Activar cuenta con token",
    dependencies=[Depends(RateLimitDep(endpoint="auth:activation", key_type="ip"))],
)
async def activate(
    payload: ActivationRequest,
    request: Request,
    facade: AuthFacade = Depends(get_auth_facade),
):
    """
    Activa una cuenta a partir de un token enviado por correo electrónico.
    Rate limited: 5 requests / 10 min por IP.
    """
    # Inyectar metadatos de request para auditoría
    meta = get_request_meta(request)
    data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
    data.update(meta)
    return await facade.activate_account(data)


@router.post(
    "/activation/resend",
    response_model=MessageResponse,
    summary="Reenviar correo de activación",
    dependencies=[
        Depends(RateLimitDep(
            endpoint="auth:activation_resend",
            key_type="ip",
            limit=3,
            window_sec=600,
        )),
        Depends(RateLimitDep(
            endpoint="auth:activation_resend",
            key_type="email",
            limit=2,
            window_sec=900,
        )),
    ],
)
async def resend_activation(
    payload: ResendActivationRequest,
    request: Request,
    facade: AuthFacade = Depends(get_auth_facade),
):
    """
    Reenvía el correo de activación si la cuenta aún no está activa.
    
    Rate limited:
      - 3 requests por IP cada 10 min
      - 2 requests por email cada 15 min
    
    SEGURIDAD: Siempre responde 200 con mensaje genérico.
    """
    # Inyectar metadatos de request para auditoría
    meta = get_request_meta(request)
    data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
    data.update(meta)
    
    return await facade.resend_activation_email(data)


@router.post(
    "/password/forgot",
    response_model=MessageResponse,
    summary="Iniciar restablecimiento de contraseña",
    dependencies=[
        Depends(RateLimitDep(endpoint="auth:forgot", key_type="ip")),
        Depends(RateLimitDep(endpoint="auth:forgot", key_type="email")),
    ],
)
async def forgot_password(
    payload: PasswordResetRequest,
    request: Request,
    facade: AuthFacade = Depends(get_auth_facade),
):
    """
    Inicia el flujo de restablecimiento de contraseña.

    Rate limited:
      - Por IP (default limits)
      - Por email (default limits)

    No revela si el email existe o no en el sistema por motivos de seguridad.
    
    SEGURIDAD ANTI-SPOOFING:
    ip_address y user_agent se inyectan desde request headers (no del body).
    El orden de merge garantiza que meta SIEMPRE sobrescribe cualquier valor del body.
    """
    # 1. Convertir payload a dict (Pydantic filtra campos no definidos en schema)
    data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
    
    # 2. Obtener meta de request headers (ip_address, user_agent)
    meta = get_request_meta(request)
    
    # 3. ANTI-SPOOFING: meta.update() al final garantiza que ip_address/user_agent
    #    se obtienen del request real, no del body
    data.update(meta)
    
    return await facade.forgot_password(data)


@router.post(
    "/password/reset",
    response_model=MessageResponse,
    summary="Confirmar restablecimiento de contraseña",
    dependencies=[Depends(RateLimitDep(endpoint="auth:reset", key_type="ip"))],
)
async def reset_password(
    payload: PasswordResetConfirmRequest,
    request: Request,
    facade: AuthFacade = Depends(get_auth_facade),
):
    """
    Confirma el restablecimiento de contraseña usando un token válido y una nueva contraseña.
    Rate limited: 5 requests / 10 min por IP.
    
    SEGURIDAD ANTI-SPOOFING:
    ip_address y user_agent se inyectan desde request headers (no del body).
    El orden de merge garantiza que meta SIEMPRE sobrescribe cualquier valor del body.
    """
    # 1. Obtener meta de request headers (ip_address, user_agent)
    meta = get_request_meta(request)
    
    # 2. Convertir payload a dict
    data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
    
    # 3. ANTI-SPOOFING: meta.update() al final garantiza que ip_address/user_agent
    #    del body se sobrescriben con los valores reales del request
    data.update(meta)
    
    return await facade.reset_password(data)


# Fin del script backend/app/modules/auth/routes/auth_public.py
