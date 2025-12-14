
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/utils/recaptcha_helpers.py

Helpers para verificación de reCAPTCHA, desacoplados de los servicios
de alto nivel.

Autor: Ixchel Beristain
Fecha: 19/11/2025
"""

from __future__ import annotations

from typing import Optional, Any

from fastapi import HTTPException, status

from app.shared.config.config_loader import get_settings
from app.shared.integrations.recaptcha_adapter import verify_recaptcha


async def verify_recaptcha_or_raise(
    token: Optional[str],
    recaptcha_verifier: Optional[Any] = None,
) -> None:
    """
    Verifica un token de reCAPTCHA y lanza HTTPException si no es válido.

    Si RECAPTCHA_ENABLED=False en settings, no hace nada.
    """
    settings = get_settings()
    if not getattr(settings, "RECAPTCHA_ENABLED", False):
        return

    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Falta token de reCAPTCHA.",
        )

    if recaptcha_verifier is not None:
        ok = await recaptcha_verifier.verify(token)
    else:
        ok = await verify_recaptcha(token)

    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reCAPTCHA inválido.",
        )


__all__ = ["verify_recaptcha_or_raise"]

# Fin del script backend/app/modules/auth/utils/recaptcha_helpers.py
