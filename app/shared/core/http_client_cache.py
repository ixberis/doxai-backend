# -*- coding: utf-8 -*-
"""
backend/app/shared/core/http_client_cache.py

Gestión del cliente HTTP global compartido.
Proporciona configuración optimizada para requests concurrentes.

Requisitos:
- httpx>=0.26.0 (para soporte de AsyncHTTPTransport con parámetro 'retries')

Autor: Ixchel Beristain
Fecha: 05/09/2025
Actualizado:
- 2025-10-24: Extraído de resource_cache.py para mejor modularidad
"""

from __future__ import annotations
import asyncio
import httpx
import logging
import os

from .resources_cache import resources

logger = logging.getLogger(__name__)

# Lock async para evitar creación concurrente del cliente HTTP
_http_client_lock = asyncio.Lock()


async def create_http_client() -> bool:
    """
    Crea el cliente HTTP global compartido.
    Thread-safe y protegido contra creación concurrente con asyncio.Lock.
    Soporta User-Agent identificable, base_url y proxies desde settings.
    """
    async with _http_client_lock:
        try:
            # Obtener settings para configuración dinámica
            from app.shared.config import get_settings
            settings = get_settings()
            
            logger.info("🔗 Inicializando cliente HTTP global...")

            # Cerrar cliente previo si existe (prevención de fugas en re-init/tests)
            if resources.http_client is not None:
                try:
                    await resources.http_client.aclose()
                    logger.debug("Cliente HTTP previo cerrado correctamente")
                except Exception as e:
                    logger.debug(f"No se pudo cerrar cliente HTTP previo: {e}")

            # Headers identificables (User-Agent) + cabeceras extra opcionales
            headers = {
                "User-Agent": f"{settings.app_name}/{settings.app_version} (+https://doxai.juvare.mx)",
                **(settings.http_extra_headers or {})
            }

            # Configuración de timeouts y límites
            timeout = httpx.Timeout(connect=10.0, read=120.0, write=120.0, pool=120.0)
            limits = httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
                keepalive_expiry=30.0,
            )
            transport = httpx.AsyncHTTPTransport(retries=2)

            # Proxies desde settings (opcional)
            proxies = None
            if settings.http_proxy:
                proxies = {
                    "http://": settings.http_proxy,
                    "https://": settings.http_proxy,
                }
                logger.debug(f"HTTP proxy configurado: {settings.http_proxy}")

            # Configurar NO_PROXY si está definido
            trust_env = True
            if settings.http_no_proxy:
                os.environ["NO_PROXY"] = settings.http_no_proxy
                os.environ["no_proxy"] = settings.http_no_proxy  # Compatibilidad lowercase
                logger.debug(f"NO_PROXY configurado: {settings.http_no_proxy}")

            # Crear cliente con configuración completa
            resources.http_client = httpx.AsyncClient(
                base_url=settings.http_base_url or None,  # Evita pasar cadenas vacías
                headers=headers,
                timeout=timeout,
                limits=limits,
                transport=transport,
                proxies=proxies,
                trust_env=trust_env,
            )

            logger.info("✅ Cliente HTTP global inicializado")
            return True

        except Exception as e:
            logger.error(f"❌ Error inicializando cliente HTTP: {e}")
            return False


async def get_http_client() -> httpx.AsyncClient:
    """
    Obtiene el cliente HTTP global. Si no existe, lo crea.
    """
    if resources.http_client is None:
        logger.info("🔗 Cliente HTTP no inicializado, creando...")
        ok = await create_http_client()
        if not ok:
            raise RuntimeError("No fue posible inicializar el cliente HTTP global")
    return resources.http_client


# Fin del archivo backend/app/shared/core/http_client_cache.py
