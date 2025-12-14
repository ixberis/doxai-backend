
# -*- coding: utf-8 -*-
"""
backend/app/core/__init__.py

Fachada unificada para componentes centrales del backend DoxAI 2.0:
- Configuración (settings)
- Logging
- Motor de base de datos y sesiones

Esta capa envuelve la implementación existente en `app.shared.*` para
ofrecer puntos de entrada estables hacia el resto de los módulos.

Autor: Ixchel Beristain
Fecha: 2025-11-17
"""

from .settings import get_settings
from .logging import setup_logging
from .db import (
    engine,
    SessionLocal,
    Base,
    get_async_session,
    get_db,
    session_scope,
    check_database_health,
)

__all__ = [
    "get_settings",
    "setup_logging",
    "engine",
    "SessionLocal",
    "Base",
    "get_async_session",
    "get_db",
    "session_scope",
    "check_database_health",
]

# Fin del archivo backend\app\core\__init__.py