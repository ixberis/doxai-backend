# -*- coding: utf-8 -*-
"""
backend/app/modules/admin/routes/__init__.py

Punto de entrada de rutas del módulo Admin.

Expone una función helper `get_admin_routers()` para ser usada por la app principal.

Autor: Ixchel Beristain
Fecha: 05/11/2025
"""

from .cache_routes import router as cache_router
from .scheduler_routes import router as scheduler_router
from .users_routes import router as users_router


def get_admin_routers():
    """
    Retorna la lista de routers del módulo Admin.
    
    Returns:
        Lista de APIRouter
    """
    return [cache_router, scheduler_router, users_router]


__all__ = ["get_admin_routers", "cache_router", "scheduler_router", "users_router"]
