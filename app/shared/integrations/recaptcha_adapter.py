
# -*- coding: utf-8 -*-
"""
backend/app/shared/integrations/recaptcha_adapter.py

Adapter para verificación de reCAPTCHA v2/v3 con feature flag.
En local/test puede hacer bypass para no frenar el desarrollo.

FIXED: Ahora usa httpx async para evitar bloqueos del event loop.

Autor: Ixchel Beristain
Actualizado: 20/10/2025
"""

import os
import logging
import httpx
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

RECAPTCHA_ENABLED = os.getenv("RECAPTCHA_ENABLED", "false").strip().lower() in ("1", "true", "yes")
RECAPTCHA_SECRET = os.getenv("RECAPTCHA_SECRET", "").strip()
RECAPTCHA_TIMEOUT = int(os.getenv("RECAPTCHA_TIMEOUT_SEC", "8"))
VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"


async def verify_recaptcha(token: str | None) -> bool:
    """
    Devuelve True si reCAPTCHA es válido o está deshabilitado por flag.
    
    IMPORTANTE: Usa httpx async para no bloquear el event loop.
    """
    if not RECAPTCHA_ENABLED:
        logger.debug("reCAPTCHA deshabilitado por flag, bypass automático")
        return True
    
    if not token or not RECAPTCHA_SECRET:
        logger.warning("reCAPTCHA habilitado pero falta token o secret")
        return False

    try:
        async with httpx.AsyncClient(timeout=RECAPTCHA_TIMEOUT) as client:
            response = await client.post(
                VERIFY_URL,
                data={"secret": RECAPTCHA_SECRET, "response": token}
            )
            
            if response.status_code != 200:
                logger.error(f"reCAPTCHA API error: HTTP {response.status_code}")
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="Error al verificar reCAPTCHA con Google"
                )
            
            payload = response.json()
            success = bool(payload.get("success", False))
            
            if not success:
                errors = payload.get("error-codes", [])
                logger.warning(f"reCAPTCHA verification failed: {errors}")
            
            return success
            
    except httpx.TimeoutException:
        logger.error(f"reCAPTCHA timeout después de {RECAPTCHA_TIMEOUT} segundos")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Timeout verificando reCAPTCHA ({RECAPTCHA_TIMEOUT}s)"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error inesperado en verify_recaptcha: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno verificando reCAPTCHA"
        )

# Fin del script recaptcha_adapter.py