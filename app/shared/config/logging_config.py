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

# Flag global para evitar múltiples prints de confirmación
_LOGGING_SETUP_ONCE = False

# Niveles válidos para MULTIPART_LOG_LEVEL
_VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})

# Loggers de multipart a silenciar (cobertura completa)
_MULTIPART_LOGGER_NAMES = (
    "multipart",
    "multipart.multipart",
    "python_multipart",
    "python_multipart.multipart",
)

# Loggers de aiosqlite a silenciar (muy verbosos en DEBUG)
_AIOSQLITE_LOGGER_NAMES = (
    "aiosqlite",
    "aiosqlite.core",
)

# Todos los loggers ruidosos combinados
_NOISY_LOGGER_NAMES = _MULTIPART_LOGGER_NAMES + _AIOSQLITE_LOGGER_NAMES


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
    global _LOGGING_SETUP_ONCE
    
    # Normalización de formato (pretty == plain para efectos prácticos)
    use_json = fmt == "json"
    
    # Detectar si pythonjsonlogger está disponible
    json_formatter_path: str | None = None
    if use_json:
        try:
            import importlib
            # v4+ usa pythonjsonlogger.json
            importlib.import_module("pythonjsonlogger.json")
            json_formatter_path = "pythonjsonlogger.json.JsonFormatter"
        except ImportError:
            try:
                # v3.x usa pythonjsonlogger.jsonlogger
                importlib.import_module("pythonjsonlogger.jsonlogger")
                json_formatter_path = "pythonjsonlogger.jsonlogger.JsonFormatter"
            except ImportError:
                # pythonjsonlogger no instalado - fallback a plain
                print(
                    "WARNING [logging_config]: fmt='json' solicitado pero pythonjsonlogger "
                    "no está instalado. Usando formato plain.",
                    file=sys.stderr,
                )
                use_json = False
    
    # Formatters base
    formatters: dict = {
        "default": {
            "format": "%(levelname)s [%(name)s]: %(message)s"
        },
    }
    
    # Solo agregar formatter json si está disponible
    if json_formatter_path:
        formatters["json"] = {
            "()": json_formatter_path,
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s"
        }
    
    handlers = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if use_json else "default",
            "stream": "ext://sys.stdout",
        }
    }
    
    # Nivel dinámico para loggers multipart (via env var)
    multipart_level = _get_multipart_log_level()
    
    # Loggers ruidosos - silenciarlos completamente
    # handlers=[] explícito + propagate=False = silencio total garantizado
    noisy_loggers = {
        name: {
            "handlers": [],  # Explícito: sin handlers
            "level": multipart_level,  # Mismo nivel para todos (configurable via MULTIPART_LOG_LEVEL)
            "propagate": False,
        }
        for name in _NOISY_LOGGER_NAMES
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
        "loggers": noisy_loggers,
    }
    
    logging.config.dictConfig(logging_config)
    
    # HARD-OVERRIDE: Aplicar configuración imperativa a todos los loggers ruidosos
    # Esto garantiza silencio incluso si otro dictConfig/basicConfig corre después
    _apply_noisy_loggers_hard_override(multipart_level)
    
    # Log de startup con niveles efectivos
    _log_noisy_logger_levels(multipart_level)
    
    # Print a stderr (no depende de logging) - solo una vez
    if not _LOGGING_SETUP_ONCE:
        _LOGGING_SETUP_ONCE = True
        git_sha = os.environ.get("RAILWAY_GIT_COMMIT_SHA", os.environ.get("GIT_SHA", "local"))[:8]
        env = os.environ.get("ENVIRONMENT", "development")
        print(
            f"LOGGING_SETUP_RAN build={git_sha} env={env} "
            f"multipart_level={multipart_level} root_level={level}",
            file=sys.stderr,
        )


def _apply_noisy_loggers_hard_override(level_str: str) -> None:
    """
    Aplica configuración imperativa a todos los loggers ruidosos.
    
    Esto es defensa contra uvicorn/gunicorn u otros módulos que
    puedan llamar dictConfig/basicConfig después de nosotros.
    
    Args:
        level_str: Nivel de logging (e.g., "WARNING", "DEBUG")
    """
    import logging
    level = getattr(logging, level_str, logging.WARNING)
    
    for name in _NOISY_LOGGER_NAMES:
        logger = logging.getLogger(name)
        # Forzar nivel
        logger.setLevel(level)
        # Evitar propagación al root (que tiene handler activo)
        logger.propagate = False
        # Limpiar cualquier handler que pueda existir
        logger.handlers.clear()


def _log_noisy_logger_levels(configured_level: str) -> None:
    """Emite log de startup con niveles efectivos de loggers ruidosos."""
    import logging
    levels = {
        name: logging.getLevelName(logging.getLogger(name).getEffectiveLevel())
        for name in _NOISY_LOGGER_NAMES
    }
    app_logger = logging.getLogger("app.shared.config.logging_config")
    app_logger.info("noisy_loggers_configured: level=%s levels=%s", configured_level, levels)


def get_multipart_logger_states() -> list[dict]:
    """
    Retorna estado actual de cada logger multipart.
    Útil para verificación en startup.
    """
    import logging
    states = []
    for name in _MULTIPART_LOGGER_NAMES:
        logger = logging.getLogger(name)
        states.append({
            "name": name,
            "level": logging.getLevelName(logger.level),
            "effective_level": logging.getLevelName(logger.getEffectiveLevel()),
            "propagate": logger.propagate,
            "handlers_count": len(logger.handlers),
        })
    return states


def get_noisy_logger_states() -> list[dict]:
    """
    Retorna estado actual de todos los loggers ruidosos (multipart + aiosqlite).
    Útil para verificación en startup.
    """
    import logging
    states = []
    for name in _NOISY_LOGGER_NAMES:
        logger = logging.getLogger(name)
        states.append({
            "name": name,
            "level": logging.getLevelName(logger.level),
            "effective_level": logging.getLevelName(logger.getEffectiveLevel()),
            "propagate": logger.propagate,
            "handlers_count": len(logger.handlers),
        })
    return states


__all__ = ["setup_logging", "get_multipart_logger_states", "get_noisy_logger_states"]
# Fin del archivo backend/app/shared/config/logging_config.py
