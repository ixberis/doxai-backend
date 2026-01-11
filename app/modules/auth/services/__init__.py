# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/__init__.py

Punto de entrada del paquete services de Auth.
Expone dependencias y utilidades usadas por rutas y otros módulos.

Re-exports get_current_user directly from token_service to avoid double lookups.
token_service.get_current_user: ORM mode, single lookup, instrumented.
token_service.get_current_user_ctx: Core mode, faster, returns AuthContextDTO.
token_service.get_current_user_id: Core mode, returns UUID string.

Autor: Ixchel Beristain
Actualizado: 18/10/2025
Updated: 2026-01-11 - Fix double lookup: re-export from token_service instead of wrapping.
"""

from __future__ import annotations

# Direct re-exports from token_service (single source of truth)
from app.modules.auth.services.token_service import (
    get_current_user,      # ORM mode: returns AppUser, single lookup, instrumented
    get_current_user_ctx,  # Core mode: returns AuthContextDTO, faster
    get_current_user_id,   # Core mode: returns auth_user_id as string
    get_optional_user_id,  # Core mode: returns auth_user_id or None if not authenticated
)

# Export explícito de lo que otros módulos suelen importar
__all__ = [
    "get_current_user",       # retro-compatibilidad (ORM, single lookup)
    "get_current_user_ctx",   # Core, fastest for auth context only
    "get_current_user_id",    # Core, returns UUID string
    "get_optional_user_id",   # Core, returns None if not authenticated
]

# Fin del archivo

