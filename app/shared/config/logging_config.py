# -*- coding: utf-8 -*-
"""
backend/app/shared/config/logging_config.py

Configuración centralizada de logging para DoxAI.
Soporta formato plain (desarrollo) y json (producción).

Autor: Ixchel Beristain
Fecha: 24/10/2025
"""

import logging.config
from typing import Literal


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
    
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": formatters,
        "handlers": handlers,
        "root": {
            "handlers": ["console"],
            "level": level.upper(),
        },
    }
    
    logging.config.dictConfig(logging_config)


__all__ = ["setup_logging"]
# Fin del archivo backend/app/shared/config/logging_config.py
