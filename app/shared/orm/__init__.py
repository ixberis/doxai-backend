# -*- coding: utf-8 -*-
"""
backend/app/shared/orm/__init__.py

Módulo de configuración ORM compartida.

Exporta utilidades para registro de relaciones cross-module.
"""

from .cross_module_relationships import (
    register_cross_module_relationships,
    reset_registration_flag,
)

__all__ = [
    "register_cross_module_relationships",
    "reset_registration_flag",
]
