# -*- coding: utf-8 -*-
"""
PDF Conversion Configuration - Settings and configuration helpers.
"""

from typing import Any
import logging

logger = logging.getLogger(__name__)


def get_settings():
    """Helper para acceder a settings con import lazy."""
    from app.shared.config import settings
    return settings


def get_hi_res_timeout() -> int:
    """Obtiene timeout hi_res desde settings o fallback."""
    try:
        return get_settings().DOXAI_HI_RES_TIMEOUT
    except Exception:
        return 25  # Fallback reducido de 45s a 25s para mejor rendimiento


def get_hi_res_max_pages() -> int:
    """Obtiene máximo de páginas hi_res desde settings."""
    try:
        settings = get_settings()
        return max(0, int(getattr(settings, "DOXAI_HI_RES_MAX_PAGES", 10)))
    except Exception:
        return 10  # Aumentado de 3 a 10 para PDFs escaneados


def should_use_fast_strategy() -> bool:
    """Determina si usar solo estrategia fast."""
    try:
        settings = get_settings()
        return (settings.DOXAI_CONVERT_STRATEGY == "fast" and 
                not settings.DOXAI_FORCE_HI_RES)
    except Exception:
        return False


def should_process_hi_res(strict_table_mode: bool) -> bool:
    """Determina si procesar hi_res basado en configuración."""
    try:
        settings = get_settings()
        return (strict_table_mode or 
                settings.DOXAI_CONVERT_STRATEGY in ("adaptive", "hi_res"))
    except Exception:
        return False


def should_force_all_pages_hi_res() -> bool:
    """Determina si forzar hi_res en todas las páginas."""
    try:
        settings = get_settings()
        return (settings.DOXAI_CONVERT_STRATEGY == "hi_res" or 
                settings.DOXAI_FORCE_HI_RES)
    except Exception:
        return False


def allow_partial_results() -> bool:
    """Determina si permitir resultados parciales en caso de error."""
    try:
        settings = get_settings()
        return bool(getattr(settings, "DOXAI_CONVERSION_RETURN_PARTIAL_ON_TIMEOUT", True))
    except Exception:
        return True


def get_target_element_count() -> int:
    """Obtiene el conteo objetivo de elementos."""
    try:
        settings = get_settings()
        return getattr(settings, "DOXAI_TARGET_ELEMENT_COUNT", 900)
    except Exception:
        return 900


def get_element_count_warning_range() -> tuple:
    """Obtiene el rango de advertencia para el conteo de elementos."""
    try:
        settings = get_settings()
        return getattr(settings, "DOXAI_ELEMENT_COUNT_WARNING_RANGE", (750, 1050))
    except Exception:
        return (750, 1050)






