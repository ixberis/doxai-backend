
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
"""

from __future__ import annotations

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

# Tag único para identificación en montaje (Swagger agrupa bajo "auth")
router = APIRouter(prefix="/auth", tags=["auth-public"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registro de usuario",
)
async def register(
    payload: RegisterRequest,
    request: Request,
    facade: AuthFacade = Depends(get_auth_facade),
):
    """
    Registra un nuevo usuario en la plataforma.

    Flujo:
      1. Verificación de reCAPTCHA (si está habilitado en settings).
      2. Validación de unicidad de correo.
      3. Creación del usuario.
      4. Emisión de token de activación.
      5. Envío de correo de activación.
    """
    # Inyectar metadatos de request para auditoría
    meta = get_request_meta(request)
    data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
    data.update(meta)
    return await facade.register_user(data)


@router.post(
    "/activation",
    response_model=MessageResponse,
    summary="Activar cuenta con token",
)
async def activate(
    payload: ActivationRequest,
    request: Request,
    facade: AuthFacade = Depends(get_auth_facade),
):
    """
    Activa una cuenta a partir de un token enviado por correo electrónico.
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
)
async def resend_activation(
    payload: ResendActivationRequest,
    facade: AuthFacade = Depends(get_auth_facade),
):
    """
    Reenvía el correo de activación si la cuenta aún no está activa.
    """
    return await facade.resend_activation_email(payload)


@router.post(
    "/password/forgot",
    response_model=MessageResponse,
    summary="Iniciar restablecimiento de contraseña",
)
async def forgot_password(
    payload: PasswordResetRequest,
    request: Request,
    facade: AuthFacade = Depends(get_auth_facade),
):
    """
    Inicia el flujo de restablecimiento de contraseña.

    No revela si el email existe o no en el sistema por motivos de seguridad.
    """
    meta = get_request_meta(request)
    data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
    data.update(meta)
    return await facade.forgot_password(data)


@router.post(
    "/password/reset",
    response_model=MessageResponse,
    summary="Confirmar restablecimiento de contraseña",
)
async def reset_password(
    payload: PasswordResetConfirmRequest,
    facade: AuthFacade = Depends(get_auth_facade),
):
    """
    Confirma el restablecimiento de contraseña usando un token válido y una nueva contraseña.
    """
    return await facade.reset_password(payload)


# Fin del script backend/app/modules/auth/routes/auth_public.py
