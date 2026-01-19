# -*- coding: utf-8 -*-
"""
backend/app/shared/config/logging_config.py

Configuración centralizada de logging para DoxAI.
Soporta formato plain (desarrollo) y json (producción).

Autor: Ixchel Beristain
Fecha: 24/10/2025
"""

import logging.config
import os
import sys
from typing import Literal

# Niveles válidos para MULTIPART_LOG_LEVEL
_VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_MULTIPART_LOGGER_NAMES = (
    "multipart",
    "multipart.multipart",
    "python_multipart",
    "python_multipart.multipart",
)


def _get_multipart_log_level() -> str:
    """
    Lee MULTIPART_LOG_LEVEL de env, normaliza y valida.
    
    Returns:
        Nivel válido (uppercase). Default: WARNING.
    """
    raw = os.environ.get("MULTIPART_LOG_LEVEL", "WARNING")
    normalized = raw.strip().upper()
    
    if normalized in _VALID_LOG_LEVELS:
        return normalized
    
    # Valor inválido: warning a stderr y fallback
    # Nota: usamos print porque logging aún no está configurado
    print(
        f"WARNING [logging_config]: MULTIPART_LOG_LEVEL='{raw}' inválido. "
        f"Valores permitidos: {sorted(_VALID_LOG_LEVELS)}. Usando WARNING.",
        file=sys.stderr,
    )
    return "WARNING"


def setup_logging(
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO",
    fmt: Literal["plain", "pretty", "json"] = "plain"
) -> None:
    """
    Configura el sistema de logging de la aplicación.
    
    Args:
        level: Nivel de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        fmt: Formato de salida (plain, pretty, json)
        
    Ejemplos:
        >>> setup_logging("INFO", "plain")
        >>> setup_logging("DEBUG", "pretty")
        >>> setup_logging("WARNING", "json")
    """
    # Normalización de formato (pretty == plain para efectos prácticos)
    use_json = fmt == "json"
    # Resolver ruta correcta del JsonFormatter (v4 movió jsonlogger -> json)
    try:
        import importlib
        importlib.import_module("pythonjsonlogger.json")
        json_formatter_path = "pythonjsonlogger.json.JsonFormatter"
    except Exception:  # pragma: no cover
        json_formatter_path = "pythonjsonlogger.jsonlogger.JsonFormatter"
    
    handlers = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if use_json else "default",
            "stream": "ext://sys.stdout",
        }
    }
    
    formatters = {
        "default": {
            "format": "%(levelname)s [%(name)s]: %(message)s"
        },
        "json": {
             "()": json_formatter_path,
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s"
        },
    }
    
    # Nivel dinámico para loggers multipart (via env var)
    multipart_level = _get_multipart_log_level()
    
    # Loggers ruidosos de multipart - silenciarlos completamente
    # Sin handlers + propagate=False = silencio total
    multipart_loggers = {
        name: {
            "level": multipart_level,
            "propagate": False,
        }
        for name in _MULTIPART_LOGGER_NAMES
    }
    
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": formatters,
        "handlers": handlers,
        "root": {
            "handlers": ["console"],
            "level": level.upper(),
        },
        "loggers": multipart_loggers,
    }
    
    logging.config.dictConfig(logging_config)
    
    # Log de startup con niveles efectivos (una sola línea)
    _log_multipart_levels(multipart_level)


def _log_multipart_levels(configured_level: str) -> None:
    """Emite log de startup con niveles efectivos de loggers multipart."""
    import logging
    levels = {
        name: logging.getLevelName(logging.getLogger(name).getEffectiveLevel())
        for name in _MULTIPART_LOGGER_NAMES
    }
    app_logger = logging.getLogger("app.shared.config.logging_config")
    app_logger.info("multipart_loggers_configured: level=%s levels=%s", configured_level, levels)


__all__ = ["setup_logging"]
# Fin del archivo backend/app/shared/config/logging_config.py
