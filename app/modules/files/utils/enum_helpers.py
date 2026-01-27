# -*- coding: utf-8 -*-
"""
backend/app/modules/files/utils/enum_helpers.py

Utilidades para manejo seguro de enums que pueden llegar como string desde el ORM.

Autor: DoxAI
Fecha: 2026-01-27
"""

from __future__ import annotations

from typing import Any


def safe_enum_value(val: Any) -> str:
    """
    Extrae el valor string de un enum o string de forma segura.
    
    Usa extracción por atributo (getattr) para evitar dependencia de isinstance(Enum).
    Maneja el caso donde el ORM devuelve un string en lugar de Enum.
    
    Args:
        val: Puede ser Enum, str, o None
        
    Returns:
        String value o "null" si es None
    """
    v = getattr(val, "value", val)
    return "null" if v is None else str(v)


__all__ = ["safe_enum_value"]

# Fin del archivo backend/app/modules/files/utils/enum_helpers.py
