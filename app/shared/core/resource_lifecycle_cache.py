# -*- coding: utf-8 -*-
"""
backend/app/shared/core/resource_lifecycle_cache.py

Gestión del ciclo de vida de recursos globales.
Cierre limpio y seguro de recursos durante shutdown.

Autor: Ixchel Beristain
Fecha: 05/09/2025
Actualizado:
- 07/09/2025: Cierre blindado con shield + timeout
- 2025-10-24: Extraído de resource_cache.py para mejor modularidad
"""

from __future__ import annotations
import anyio
import logging

from .warmup_status_cache import WarmupStatus
from .resources_cache import resources

logger = logging.getLogger(__name__)


async def shutdown_all() -> None:
    """
    Cierre limpio de todos los recursos globales.

    Blindado para escenarios de cancelación (Ctrl+C) y cierre de event loop:
    - CancelScope(shield=True) evita que la cancelación interrumpa aclose().
    - move_on_after(2.0) impide que un cierre colgado bloquee el shutdown.
    - Captura de RuntimeError('Event loop is closed') para salida silenciosa.
    """
    logger.info("🔴 Cerrando recursos globales...")

    # HTTP client
    client = getattr(resources, "http_client", None)
    if client is not None:
        try:
            # Evita que CancelledError interrumpa el cierre
            with anyio.CancelScope(shield=True):
                # Dar una ventana breve para cerrar con gracia
                with anyio.move_on_after(2.0):
                    await client.aclose()
        except RuntimeError as e:
            # Si el loop ya se cerró, no se puede cerrar el cliente; solo advertir
            if "Event loop is closed" in str(e):
                logger.warning("Event loop ya cerrado al cerrar http client; se ignora.")
            else:
                logger.exception("Error cerrando http client (RuntimeError): %s", e)
        except Exception as e:
            logger.exception("Error cerrando http client: %s", e)
        finally:
            resources.http_client = None
            logger.info("✅ Cliente HTTP cerrado")

    # Reset de warmup
    resources.warmup_completed = False
    resources.warmup_status = WarmupStatus()

    logger.info("🔴 Recursos globales cerrados")


# Fin del archivo backend/app/shared/core/resource_lifecycle_cache.py
