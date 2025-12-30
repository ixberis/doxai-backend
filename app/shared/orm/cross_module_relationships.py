# -*- coding: utf-8 -*-
"""
backend/app/shared/orm/cross_module_relationships.py

Registro de relaciones ORM entre módulos.

NOTA: El módulo legacy 'payments' fue eliminado. Las relaciones
cross-module para billing se manejan directamente en los modelos
de billing si es necesario.

Este archivo se mantiene para compatibilidad con código que
llama a register_cross_module_relationships().

Autor: DoxAI
Fecha: 2025-12-23 (refactored 2025-12-30)
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_RELATIONSHIPS_REGISTERED = False


def register_cross_module_relationships() -> None:
    """
    Registra relaciones ORM entre módulos.
    
    NOTA: El módulo legacy 'payments' fue eliminado.
    Esta función ahora es un no-op pero se mantiene para
    compatibilidad con código que la invoca al startup.
    """
    global _RELATIONSHIPS_REGISTERED
    
    if _RELATIONSHIPS_REGISTERED:
        logger.debug("Cross-module relationships already registered, skipping.")
        return
    
    # El módulo payments fue eliminado.
    # Las relaciones de billing se manejan directamente.
    logger.info("Cross-module relationships: payments module removed, no relations to register.")
    
    _RELATIONSHIPS_REGISTERED = True


def reset_registration_flag() -> None:
    """
    Resetea el flag de registro (solo para tests).
    
    NO usar en producción.
    """
    global _RELATIONSHIPS_REGISTERED
    _RELATIONSHIPS_REGISTERED = False


__all__ = ["register_cross_module_relationships", "reset_registration_flag"]
