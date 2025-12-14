
# -*- coding: utf-8 -*-
"""
backend/app/core/logging.py

Configuración centralizada de logging para DoxAI 2.0.
Actúa como fachada del módulo `app.shared.config.logging_config` para
mantener un punto de entrada único bajo `app.core`.

Autor: Ixchel Beristain
Fecha: 2025-11-17
"""

from typing import Literal

from app.shared.config.logging_config import setup_logging as _setup_logging


def setup_logging(
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO",
    fmt: Literal["plain", "pretty", "json"] = "plain",
) -> None:
    """
    Configura el sistema de logging de la aplicación.

    Args:
        level: Nivel de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        fmt: Formato de salida (plain, pretty, json).
    """
    _setup_logging(level=level, fmt=fmt)

# Fin del archivo backend\app\core\logging.py