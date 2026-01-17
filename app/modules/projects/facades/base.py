
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/base.py

Utilidades base compartidas por todos los facades de proyectos.
Helpers de sesión, timestamps y operaciones transaccionales.

Autor: Ixchel Beristain
Fecha: 2025-10-26
Actualizado: 2026-01-16 - commit_or_raise robusto para AsyncSession/Session
"""

import datetime as dt
import inspect
from typing import Callable, TypeVar, Union, Awaitable

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar('T')


def now_utc() -> dt.datetime:
    """
    Retorna timestamp actual UTC.
    
    Centralizado para facilitar testing con mocks.
    
    Returns:
        datetime UTC actual
    """
    return dt.datetime.now(dt.timezone.utc)


def _is_async_session(db) -> bool:
    """
    Detecta si db es una AsyncSession de forma robusta.
    
    Usa isinstance() en lugar de heurísticas frágiles como hasattr.
    """
    return isinstance(db, AsyncSession)


async def commit_or_raise(db: Union[Session, AsyncSession], work: Callable[[], T]) -> T:
    """
    Ejecuta work() dentro de un contexto transaccional.
    
    Aplica commit si work() tiene éxito.
    Aplica rollback y re-lanza si work() falla.
    
    NOTA: El caller es responsable de hacer db.refresh() si necesita
    acceder a atributos del objeto ORM post-commit (evita MissingGreenlet).
    
    Soporta:
    - db siendo AsyncSession o Session
    - work siendo sync o async (awaitable)
    
    Args:
        db: Sesión SQLAlchemy (Session o AsyncSession)
        work: Función a ejecutar dentro de la transacción
        
    Returns:
        Resultado de work()
        
    Raises:
        Cualquier excepción lanzada por work()
    """
    is_async = _is_async_session(db)
    
    try:
        # Ejecutar work
        result = work()
        
        # Si result es awaitable (coroutine), await it
        if inspect.isawaitable(result):
            result = await result
        
        # Commit según tipo de sesión
        if is_async:
            await db.commit()
        else:
            db.commit()
        
        return result
        
    except Exception:
        # Rollback según tipo de sesión
        if is_async:
            await db.rollback()
        else:
            db.rollback()
        raise


__all__ = [
    "now_utc",
    "commit_or_raise",
    "_is_async_session",
]
# Fin del archivo backend/app/modules/projects/facades/base.py
