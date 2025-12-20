
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/utils/recaptcha_helpers.py

Helpers para verificación de reCAPTCHA/CAPTCHA, desacoplados de los servicios
de alto nivel.

Incluye logging de auditoría para intentos de validación.

Autor: Ixchel Beristain
Fecha: 19/11/2025
Actualizado: 2025-12-20 - Agregado logging de auditoría
"""

from __future__ import annotations

import logging
from typing import Optional, Any

from fastapi import HTTPException, status

from app.shared.config.config_loader import get_settings
from app.shared.integrations.recaptcha_adapter import verify_recaptcha

logger = logging.getLogger(__name__)


async def verify_recaptcha_or_raise(
    token: Optional[str],
    recaptcha_verifier: Optional[Any] = None,
    *,
    action: str = "unknown",
    ip_address: str = "unknown",
) -> None:
    """
    Verifica un token de reCAPTCHA/CAPTCHA y lanza HTTPException si no es válido.

    Si RECAPTCHA_ENABLED=False en settings, no hace nada.
    
    Args:
        token: Token de CAPTCHA del cliente
        recaptcha_verifier: Verificador inyectado (para tests)
        action: Acción que se está protegiendo (para logs)
        ip_address: IP del cliente (para logs, NO el token)
    
    Raises:
        HTTPException 400: Si el token falta o es inválido
    
    Logs:
        - captcha_validation_success action=... ip=...
        - captcha_validation_failed action=... ip=... reason=...
    """
    settings = get_settings()
    if not getattr(settings, "RECAPTCHA_ENABLED", False):
        return

    if not token:
        logger.warning(
            "captcha_validation_failed action=%s ip=%s reason=missing_token",
            action,
            ip_address,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "No se pudo verificar que eres humano. Intenta nuevamente.",
                "error_code": "captcha_missing",
            },
        )

    # Verificar con el servicio (mock o real)
    if recaptcha_verifier is not None:
        ok = await recaptcha_verifier.verify(token)
    else:
        ok = await verify_recaptcha(token)

    if not ok:
        logger.warning(
            "captcha_validation_failed action=%s ip=%s reason=invalid_token",
            action,
            ip_address,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "No se pudo verificar que eres humano. Intenta nuevamente.",
                "error_code": "captcha_invalid",
            },
        )

    # Éxito
    logger.info(
        "captcha_validation_success action=%s ip=%s",
        action,
        ip_address,
    )


__all__ = ["verify_recaptcha_or_raise"]

# Fin del script backend/app/modules/auth/utils/recaptcha_helpers.py
