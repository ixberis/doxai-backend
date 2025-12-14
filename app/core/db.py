
# -*- coding: utf-8 -*-
"""
backend/app/core/db.py

Fachada para la capa de acceso a datos basada en SQLAlchemy async.
Envuelve el módulo `app.shared.database.database` para exponer un
conjunto claro de primitivas de acceso a la base de datos:

- engine
- SessionLocal
- Base
- get_async_session / get_db
- session_scope()
- check_database_health()

Autor: Ixchel Beristain
Fecha: 2025-11-17
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.shared.database.database import (
    engine,
    SessionLocal,
    Base,
    get_async_session,
    get_db,
    session_scope,
    check_database_health,
)


__all__ = [
    "engine",
    "SessionLocal",
    "Base",
    "get_async_session",
    "get_db",
    "session_scope",
    "check_database_health",
]


# Reexportamos tipos para que el resto del código pueda tipar
# sin acoplarse a `app.shared`.
DeclarativeBase = DeclarativeBase


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependencia FastAPI para obtener una sesión asíncrona de base de datos.

    Esta función simplemente envuelve `get_async_session` pero la expone
    bajo `app.core.db`, de modo que los módulos de DoxAI 2.0 puedan
    depender de esta capa sin conocer la implementación interna.

    Yields:
        AsyncSession: sesión asíncrona de SQLAlchemy.
    """
    async for session in get_async_session():
        yield session

# Fin del archivo backend\app\core\db.py