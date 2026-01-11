# -*- coding: utf-8 -*-
"""
backend/app/shared/database/statement_counter.py

Contador global de statements SQL usando ContextVar para aislamiento por request.
Permite medir el número exacto de queries ejecutadas en cualquier contexto async.

Autor: Ixchel Beristain
Fecha: 2025-01-11
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# ContextVar para aislamiento por request/task
_statement_counter: ContextVar[Optional["StatementCounter"]] = ContextVar(
    "statement_counter", default=None
)


@dataclass
class StatementCounter:
    """Contador de statements SQL por contexto."""
    count: int = 0
    statements: list[str] = field(default_factory=list)
    capture_sql: bool = False  # Si True, guarda el SQL (solo para debug)
    
    def increment(self, sql: str = "") -> None:
        self.count += 1
        if self.capture_sql and sql:
            # Solo guardar primeros 200 chars para evitar memory issues
            self.statements.append(sql[:200])


def get_counter() -> Optional[StatementCounter]:
    """Obtiene el contador del contexto actual."""
    return _statement_counter.get()


def start_counting(capture_sql: bool = False) -> StatementCounter:
    """
    Inicia un nuevo contador en el contexto actual.
    
    Args:
        capture_sql: Si True, captura el SQL de cada statement (solo debug)
        
    Returns:
        El nuevo contador
    """
    counter = StatementCounter(capture_sql=capture_sql)
    _statement_counter.set(counter)
    return counter


def stop_counting() -> Optional[StatementCounter]:
    """
    Detiene el contador y lo remueve del contexto.
    
    Returns:
        El contador final con las estadísticas
    """
    counter = _statement_counter.get()
    _statement_counter.set(None)
    return counter


def before_cursor_execute_handler(conn, cursor, statement, parameters, context, executemany):
    """
    Event handler para SQLAlchemy 'before_cursor_execute'.
    Registrar este handler una sola vez al inicializar el engine.
    """
    counter = _statement_counter.get()
    if counter is not None:
        counter.increment(statement if counter.capture_sql else "")


def setup_statement_counter(engine) -> bool:
    """
    Configura el listener global en el engine.
    Llamar una sola vez al inicializar la aplicación.
    
    Args:
        engine: SQLAlchemy sync engine
        
    Returns:
        True si se configuró correctamente
    """
    from sqlalchemy import event
    
    try:
        # Verificar si ya está registrado
        if not event.contains(engine, "before_cursor_execute", before_cursor_execute_handler):
            event.listen(engine, "before_cursor_execute", before_cursor_execute_handler)
            logger.info("statement_counter: global listener registered on engine")
            return True
        return True
    except Exception as e:
        logger.warning("statement_counter: failed to register listener: %s", e)
        return False


__all__ = [
    "StatementCounter",
    "get_counter",
    "start_counting",
    "stop_counting",
    "setup_statement_counter",
    "before_cursor_execute_handler",
]
