# -*- coding: utf-8 -*-
"""
backend/app/modules/admin/routes/__init__.py

Punto de entrada de rutas del módulo Admin.

Expone una función helper `get_admin_routers()` para ser usada por la app principal.

Autor: Ixchel Beristain
Fecha: 05/11/2025
Actualizado: 2026-01-01 - Añadido billing_finance_router
"""

from .cache_routes import router as cache_router
from .scheduler_routes import router as scheduler_router
from .users_routes import router as users_router

# Billing admin (finance + operation metrics)
try:
    from app.modules.billing.admin import billing_admin_router, billing_operation_router
    _billing_admin_available = True
except ImportError:
    billing_admin_router = None
    billing_operation_router = None
    _billing_admin_available = False


def get_admin_routers():
    """
    Retorna la lista de routers del módulo Admin.
    
    Returns:
        Lista de APIRouter
    """
    routers = [cache_router, scheduler_router, users_router]
    
    # Add billing admin routers if available
    if _billing_admin_available:
        if billing_admin_router is not None:
            routers.append(billing_admin_router)
        if billing_operation_router is not None:
            routers.append(billing_operation_router)
    
    return routers


__all__ = [
    "get_admin_routers", 
    "cache_router", 
    "scheduler_router", 
    "users_router", 
    "billing_admin_router",
    "billing_operation_router",
]
