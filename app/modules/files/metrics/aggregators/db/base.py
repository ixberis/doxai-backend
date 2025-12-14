
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/metrics/aggregators/db/base.py

Helpers comunes para agregadores DB:
- normalización de límites/offset
- utilidades de date_trunc
- manejo defensivo de excepciones

Autor: Ixchel Beristáin Mendoza
Fecha: 09/11/2025
"""
from __future__ import annotations

from typing import Any, Dict, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session


def _bounds(limit: int | None, offset: int | None, max_limit: int = 1000) -> Tuple[int, int]:
    lim = 50 if limit is None else max(1, min(int(limit), max_limit))
    off = 0 if offset is None else max(0, int(offset))
    return lim, off


def _date_trunc(day_col):
    # Devuelve expresión DATE_TRUNC('day', col)
    return func.date_trunc("day", day_col)


def safe_execute(session: Session, query):
    """
    Ejecuta una query absorbiendo errores y devolviendo lista vacía si falla.
    """
    try:
        return session.execute(query).all()
    except Exception:
        return []


def safe_dict(**kwargs: Any) -> Dict[str, Any]:
    """
    Crea un dict ignorando valores None (útil para series).
    """
    return {k: v for k, v in kwargs.items() if v is not None}


# Fin del archivo backend/app/modules/files/metrics/aggregators/db/base.py
