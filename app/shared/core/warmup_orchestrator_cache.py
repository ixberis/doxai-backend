# -*- coding: utf-8 -*-
"""
backend/app/shared/core/warmup_orchestrator_cache.py

Orquestación completa del proceso de warm-up.
Coordina verificación de herramientas, precarga de modelos y cliente HTTP.

Autor: Ixchel Beristain
Fecha: 05/09/2025
Actualizado:
- 2025-10-24: Extraído de resource_cache.py para mejor modularidad
"""

from __future__ import annotations
import time
import logging

from .warmup_status_cache import WarmupStatus
from .resources_cache import resources, _warmup_lock
from .system_tools_cache import (
    check_tesseract_availability,
    check_ghostscript_availability,
    check_poppler_availability,
)
from .warmup_preload_cache import (
    preload_unstructured_fast,
    preload_unstructured_hires,
    preload_table_model,
)
from .http_client_cache import create_http_client
from .model_singletons_cache import quiet_pdf_parsers, get_warmup_asset_path

logger = logging.getLogger(__name__)


async def run_warmup_once() -> WarmupStatus:
    """
    Ejecuta el warm-up completo una sola vez de forma idempotente.
    """
    async with _warmup_lock:
        if resources.warmup_completed:
            logger.debug("🔄 Warm-up ya completado previamente")
            return resources.warmup_status

        # Importar settings usando el singleton get_settings()
        try:
            from app.shared.config import get_settings
            settings = get_settings()
        except ImportError as e:
            # No usar settings aquí; aún no existe
            logger.error(f"❌ No se pudo importar configuración: {e}")
            raise RuntimeError("Configuración no disponible - asegúrese de que app.shared.config esté correctamente configurado") from e

        if not settings.warmup_enable:
            emoji_skip = "🚫" if settings.log_emoji else "SKIP"
            emoji_ok = "✅" if settings.log_emoji else "OK"
            logger.info(f"{emoji_skip} Warm-up deshabilitado por configuración - omitiendo precarga")
            # Marcar como completado con estado por defecto
            status = WarmupStatus()
            t0 = time.perf_counter()
            status.started_at = time.time()
            status.ended_at = time.time()
            status.duration_sec = time.perf_counter() - t0
            # Todas las precargas se marcan como OK (no requeridas)
            status.fast_ok = True
            status.hires_ok = True
            status.table_model_ok = True
            status.http_client_ok = True
            status.http_health_ok = True
            # Binarios opcionales también "verdes" para dashboards
            status.tesseract_ok = True
            status.ghostscript_ok = True
            status.poppler_ok = True
            resources.warmup_status = status
            resources.warmup_completed = True
            logger.info(f"{emoji_ok} Warm-up omitido ({status.duration_sec:.2f}s) - sistema listo sin precarga")
            return status

        status = WarmupStatus()
        t0_warmup = time.perf_counter()
        status.started_at = time.time()

        # Usar try/finally para asegurar que ended_at/duration se registren incluso con errores
        try:
            emoji_start = "🌡️" if settings.log_emoji else "START"
            emoji_ok = "✅" if settings.log_emoji else "OK"
            emoji_warn = "⚠️" if settings.log_emoji else "WARN"
            emoji_err = "❌" if settings.log_emoji else "ERR"
            
            logger.info(f"{emoji_start} Warm-up iniciando...")

            # 1. Silenciar pdfminer si está configurado
            if settings.warmup_silence_pdfminer:
                quiet_pdf_parsers()

            # 2. Verificar herramientas OCR y rasterización
            # NOTA: Estos binarios son opcionales; no bloquean is_ready
            status.tesseract_ok = check_tesseract_availability()
            status.ghostscript_ok, status.ghostscript_path = check_ghostscript_availability()
            status.poppler_ok, status.poppler_path = check_poppler_availability()

            # 3. Verificar asset de warm-up
            # CRÍTICO: Si warmup_preload_fast=True, este asset debe existir
            # Ver: backend/app/shared/core/DEPLOYMENT.md sección "Asset de warm-up"
            asset_path = get_warmup_asset_path()

            # 4. Precargar modelos de Unstructured
            if settings.warmup_preload_fast:
                if asset_path.exists():
                    try:
                        status.fast_ok = preload_unstructured_fast(asset_path, settings.warmup_timeout_sec)
                    except Exception as e:
                        error_msg = f"Error en precarga fast: {e}"
                        logger.error(f"{emoji_err} {error_msg}")
                        status.errors.append(error_msg)
                else:
                    # Asset falta pero la precarga está habilitada: ERROR
                    error_msg = f"Precarga fast habilitada pero asset no encontrado: {asset_path}"
                    logger.error(f"{emoji_err} {error_msg}")
                    status.errors.append(error_msg)
                    status.fast_ok = False
            else:
                # Precarga fast deshabilitada: marcar como OK (no requerido)
                status.fast_ok = True

            if settings.warmup_preload_hires:
                if asset_path.exists():
                    try:
                        status.hires_ok = preload_unstructured_hires(asset_path, settings.warmup_timeout_sec)
                    except Exception as e:
                        error_msg = f"Error en precarga hi_res: {e}"
                        logger.warning(f"{emoji_warn} {error_msg}")
                        status.warnings.append(error_msg)
                        # No es crítico, continuar
                else:
                    warn_msg = f"Precarga hi_res habilitada pero asset no encontrado: {asset_path}"
                    logger.warning(f"{emoji_warn} {warn_msg}")
                    status.warnings.append(warn_msg)
                    status.hires_ok = False
            else:
                # Precarga hi_res deshabilitada: marcar como OK (no requerido)
                status.hires_ok = True

            # 5. Precargar modelo de tablas
            if settings.warmup_preload_table_model:
                try:
                    status.table_model_ok = preload_table_model(settings.warmup_timeout_sec)
                except Exception as e:
                    error_msg = f"Error en precarga tabla: {e}"
                    logger.warning(f"{emoji_warn} {error_msg}")
                    status.warnings.append(error_msg)
            else:
                # Precarga tabla deshabilitada: marcar como OK (no requerido)
                status.table_model_ok = True

            # 6. Crear cliente HTTP
            # REQUISITO: httpx>=0.26.0 para AsyncHTTPTransport(retries=N)
            # Ver: backend/app/shared/core/DEPLOYMENT.md sección "Dependencias"
            if settings.warmup_http_client:
                try:
                    status.http_client_ok = await create_http_client()
                    
                    # Health check opcional durante warm-up
                    if status.http_client_ok:
                        if settings.warmup_http_health_check:
                            # Validar URL antes de hacer la llamada
                            health_url = settings.warmup_http_health_url.strip()
                            if not health_url or not (health_url.startswith('http://') or health_url.startswith('https://')):
                                warn_msg = f"URL de health-check inválida o vacía: '{health_url}' - omitiendo verificación"
                                logger.warning(f"{emoji_warn} {warn_msg}")
                                status.warnings.append(warn_msg)
                                status.http_health_ok = True  # evita falso negativo en dashboards
                            else:
                                from .http_client_cache import get_http_client
                                try:
                                    client = await get_http_client()
                                    h0 = time.perf_counter()
                                    response = await client.head(health_url, timeout=settings.warmup_http_health_timeout_sec)
                                    latency = (time.perf_counter() - h0) * 1000
                                    status.http_health_latency_ms = latency
                                    if response.status_code < 400:
                                        status.http_health_ok = True
                                        if latency > settings.warmup_http_health_warn_ms:
                                            warn_msg = f"HTTP health check lento ({latency:.0f}ms > {settings.warmup_http_health_warn_ms:.0f}ms)"
                                            logger.warning(f"{emoji_warn} {warn_msg}")
                                            status.warnings.append(warn_msg)
                                        else:
                                            logger.info(f"{emoji_ok} HTTP health check OK ({latency:.0f}ms): {health_url}")
                                    else:
                                        status.http_health_ok = False
                                        warn_msg = f"HTTP health check retornó {response.status_code}"
                                        logger.warning(f"{emoji_warn} {warn_msg}")
                                        status.warnings.append(warn_msg)
                                except Exception as e:
                                    status.http_health_ok = False
                                    warn_msg = f"HTTP health check falló: {e}"
                                    logger.warning(f"{emoji_warn} {warn_msg}")
                                    status.warnings.append(warn_msg)
                        else:
                            # Health check deshabilitado: marcar como OK (no requerido)
                            status.http_health_ok = True
                            
                except Exception as e:
                    error_msg = f"Error creando cliente HTTP: {e}"
                    logger.error(f"{emoji_err} {error_msg}")
                    status.errors.append(error_msg)
            else:
                # Cliente HTTP deshabilitado: marcar como OK (no requerido)
                status.http_client_ok = True
                status.http_health_ok = True

        finally:
            # Asegurar que ended_at y duration siempre se registren
            status.ended_at = time.time()
            status.duration_sec = time.perf_counter() - t0_warmup

            resources.warmup_status = status
            resources.warmup_completed = True

            emoji_ok = "✅" if settings.log_emoji else "OK"
            emoji_warn_sum = "🟡" if settings.log_emoji else "WARN"
            
            # Log de resumen
            logger.info(
                f"{emoji_ok} Warm-up completado en {status.duration_sec:.2f}s "
                f"(fast={status.fast_ok}, hires={status.hires_ok}, "
                f"tabla={status.table_model_ok}, http={status.http_client_ok}, "
                f"health={status.http_health_ok}, "
                f"tesseract={status.tesseract_ok}, ghostscript={status.ghostscript_ok}, "
                f"poppler={status.poppler_ok})"
            )

            if status.errors or status.warnings:
                summary_parts = []
                if status.errors:
                    summary_parts.append(f"{len(status.errors)} errores")
                if status.warnings:
                    summary_parts.append(f"{len(status.warnings)} avisos")
                logger.warning(
                    f"{emoji_warn_sum} Warm-up con {', '.join(summary_parts)}: "
                    f"errores={status.errors}, avisos={status.warnings}"
                )

        return status


async def warmup_all() -> None:
    """
    Función de compatibilidad - redirige al nuevo sistema.
    """
    await run_warmup_once()


# Fin del archivo backend/app/shared/core/warmup_orchestrator_cache.py
