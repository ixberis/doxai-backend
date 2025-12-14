
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/base.py

Utilidades base compartidas por todos los facades de proyectos.
Helpers de sesión, timestamps y operaciones transaccionales.

Autor: Ixchel Beristain
Fecha: 2025-10-26
"""

import datetime as dt
from typing import Callable, TypeVar
from sqlalchemy.orm import Session

T = TypeVar('T')


def now_utc() -> dt.datetime:
    """
    Retorna timestamp actual UTC.
    
    Centralizado para facilitar testing con mocks.
    
    Returns:
        datetime UTC actual
    """
    return dt.datetime.now(dt.timezone.utc)


def commit_or_raise(db: Session, work: Callable[[], T]) -> T:
    """
    Ejecuta work() dentro de un contexto transaccional.
    
    Aplica commit si work() tiene éxito.
    Aplica rollback y re-lanza si work() falla.
    
    Centraliza patrón try/commit/except/rollback para reducir repetición.
    
    Args:
        db: Sesión SQLAlchemy
        work: Función a ejecutar dentro de la transacción
        
    Returns:
        Resultado de work()
        
    Raises:
        Cualquier excepción lanzada por work()
    """
    try:
        result = work()
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


__all__ = [
    "now_utc",
    "commit_or_raise",
]
# Fin del archivo backend/app/modules/projects/facades/base.py
