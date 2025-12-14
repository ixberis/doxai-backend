
# -*- coding: utf-8 -*-
"""
backend/app/utils/recaptcha.py

Utilidad robusta para verificación de Google reCAPTCHA en el backend de DoxAI.

Este módulo valida el token reCAPTCHA recibido desde el frontend contra la API
oficial de Google (`/siteverify`) y está endurecido para entornos reales:
- Timeout corto y 1 reintento ante fallos transitorios de red.
- Nunca propaga excepciones: retorna (ok: bool, error_msg: str).
- Bypass automático en entorno de pruebas (`PYTHON_ENV=test`).

API pública:
    async def verify_recaptcha(token: str) -> tuple[bool, str]

Retorna:
    (True, "")                  -> verificación exitosa
    (False, "<motivo>")         -> verificación fallida o no concluyente

Notas:
- Usa `settings.recaptcha_secret_key` (Pydantic settings).
- Compatible con reCAPTCHA v2/v3 (se evalúa `success`; si deseas umbral de
  score para v3, aplícalo en la ruta llamante con los campos devueltos).
- Ante timeout/errores HTTP, devuelve False con mensaje semántico en lugar de 500.
"""

import asyncio
import logging
import os
from typing import Tuple

import httpx
from app.shared.config import settings

logger = logging.getLogger(__name__)

VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"
DEFAULT_TIMEOUT = httpx.Timeout(5.0, connect=5.0, read=5.0, write=5.0)


async def verify_recaptcha(token: str) -> Tuple[bool, str]:
    """
    Verifica un token de reCAPTCHA con tolerancia a fallos transitorios.

    Args:
        token: Token generado en el frontend por reCAPTCHA.

    Returns:
        Tuple[bool, str]: (ok, error_msg)
            - ok = True si la verificación fue exitosa.
            - ok = False y error_msg describe la causa (no lanza excepciones).
    """
    # ⚠️ Bypass para tests automáticos
    if os.getenv("PYTHON_ENV") == "test":
        return True, ""

    if not token:
        logger.warning("verify_recaptcha: token vacío")
        return False, "Token vacío"

    secret_key = getattr(settings, "recaptcha_secret_key", None)
    if not secret_key:
        logger.error("verify_recaptcha: RECAPTCHA_SECRET_KEY no configurada")
        return False, "Clave secreta no configurada"

    # Hasta 2 intentos ante timeouts transitorios
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.post(
                    VERIFY_URL,
                    data={"secret": secret_key, "response": token},
                )

                # La API de Google responde 200 incluso con errores lógicos,
                # pero validamos por si acaso.
                if resp.status_code != 200:
                    body = None
                    try:
                        body = resp.json()
                    except Exception:
                        body = resp.text
                    logger.error(
                        "verify_recaptcha: HTTP %s en siteverify: %s",
                        resp.status_code,
                        body,
                    )
                    return False, "Fallo en la API de reCAPTCHA"

                data = resp.json()
                success = bool(data.get("success"))

                if not success:
                    # Google puede regresar "error-codes"
                    errors = data.get("error-codes", [])
                    logger.warning(
                        "verify_recaptcha: validación NO exitosa: %s", errors
                    )
                    # Mensaje compacto para el caller; logs guardan detalle.
                    return False, "reCAPTCHA inválido"

                # Éxito
                return True, ""

        except (httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            logger.warning(
                "verify_recaptcha: timeout en intento %d: %r", attempt + 1, e
            )
            if attempt == 0:
                await asyncio.sleep(0.2)
                continue
            return False, "Timeout al verificar reCAPTCHA"

        except httpx.HTTPError as e:
            logger.exception("verify_recaptcha: error HTTPX: %r", e)
            return False, "Error HTTP al verificar reCAPTCHA"

        except Exception:
            logger.exception("verify_recaptcha: error inesperado")
            return False, "Excepción en la verificación"

    # Salvaguarda (no debería alcanzarse)
    return False, "Error desconocido en verificación de reCAPTCHA"






