
# -*- coding: utf-8 -*-
"""
backend/app/shared/database/__init__.py

Re-exporta utilidades comunes de base de datos.

Autor: DoxAI
Fecha: 2025-10-18 (Consolidación modular; ajustado 2025-11-21)
"""

from __future__ import annotations

from .database import (
    engine,
    SessionLocal,
    get_async_session,
    get_db,
    check_database_health,
)
from .base import Base, NAMING_CONVENTION, as_pg_enum

# Alias de compatibilidad: algunos módulos antiguos pueden importar DBBase
DBBase = Base

__all__ = [
    "engine",
    "SessionLocal",
    "Base",             # Base declarativa única
    "DBBase",           # Alias legacy -> Base
    "NAMING_CONVENTION",
    "as_pg_enum",
    "get_async_session",
    "get_db",
    "check_database_health",
]

# Fin del archivo backend/app/shared/database/__init__.py
