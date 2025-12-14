# -*- coding: utf-8 -*-
"""
backend/app/shared/core/warmup_preload_cache.py

Funciones de precarga con timeout para modelos de Unstructured.
Ejecuta warm-up de modelos con límites de tiempo y manejo de errores.

Autor: Ixchel Beristain
Fecha: 05/09/2025
Actualizado:
- 2025-10-24: Extraído de resource_cache.py para mejor modularidad
"""

from __future__ import annotations
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import logging

from .model_singletons_cache import get_fast_parser, get_table_agent, quiet_pdf_parsers

logger = logging.getLogger(__name__)


def preload_unstructured_fast(asset_path: Path, timeout_sec: int) -> bool:
    """Precarga el modelo 'fast' usando singleton con timeout."""
    try:
        logger.info("⚡ Precargando Unstructured (fast)...")

        def _run_fast():
            return get_fast_parser()  # Use singleton

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_fast)
            result = future.result(timeout=timeout_sec)

        if result:
            logger.info("✅ Unstructured (fast) precargado exitosamente")
            return True
        else:
            logger.warning("⚠️ Falló precarga de Unstructured (fast)")
            return False

    except TimeoutError:
        logger.warning(f"⚠️ Timeout precargando Unstructured fast ({timeout_sec}s)")
        return False
    except Exception as e:
        logger.warning(f"⚠️ Error precargando Unstructured fast: {e}")
        return False


def preload_unstructured_hires(asset_path: Path, timeout_sec: int) -> bool:
    """Precarga el modelo 'hi_res' usando singleton con timeout."""
    try:
        logger.info("🔍 Precargando Unstructured (hi_res)...")

        quiet_pdf_parsers()

        def _run_hires():
            return get_table_agent()  # Use singleton

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_hires)
            result = future.result(timeout=timeout_sec)

        if result:
            logger.info("✅ Unstructured (hi_res) precargado exitosamente")
            return True
        else:
            logger.warning("⚠️ Falló precarga de Unstructured (hi_res)")
            return False

    except TimeoutError:
        logger.warning(f"⚠️ Timeout precargando Unstructured hi_res ({timeout_sec}s)")
        return False
    except Exception as e:
        logger.warning(f"⚠️ Error precargando Unstructured hi_res: {e}")
        return False


def preload_table_model(timeout_sec: int) -> bool:
    """Precarga el modelo de detección de tablas usando singleton con timeout."""
    try:
        logger.info("📊 Precargando modelo de tablas...")

        def _run_table_model():
            return get_table_agent()  # Use singleton

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_table_model)
            result = future.result(timeout=timeout_sec)

        if result:
            logger.info("✅ Modelo de tablas precargado exitosamente")
            return True
        else:
            logger.warning("⚠️ Falló precarga del modelo de tablas")
            return False

    except TimeoutError:
        logger.warning(f"⚠️ Timeout precargando modelo de tablas ({timeout_sec}s)")
        return False
    except Exception as e:
        logger.warning(f"⚠️ Error precargando modelo de tablas: {e}")
        return False


# Fin del archivo backend/app/shared/core/warmup_preload_cache.py
