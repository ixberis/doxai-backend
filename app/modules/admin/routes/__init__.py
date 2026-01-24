# -*- coding: utf-8 -*-
"""
backend/app/modules/admin/routes/__init__.py

Punto de entrada de rutas del módulo Admin.

Expone una función helper `get_admin_routers()` para ser usada por la app principal.

Autor: Ixchel Beristain
Fecha: 05/11/2025
Actualizado: 2026-01-23 - Añadido projects_files_business_router
"""

from .cache_routes import router as cache_router
from .scheduler_routes import router as scheduler_router
from .users_routes import router as users_router
from .projects_files_business_routes import router as projects_files_business_router
from .projects_files_operational_routes import router as projects_files_operational_router
from .projects_files_health_routes import router as projects_files_health_router
from .projects_files_storage_routes import router as storage_router
from .projects_files_storage_routes import capture_router as storage_capture_router
from .projects_files_jobs_routes import router as jobs_router
from .projects_files_jobs_routes import prune_router as jobs_prune_router
from .projects_files_cleanup_routes import router as cleanup_router

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
    routers = [
        cache_router, 
        scheduler_router, 
        users_router,
        projects_files_business_router,
        projects_files_operational_router,
        projects_files_health_router,
        storage_router,
        storage_capture_router,
        jobs_router,
        jobs_prune_router,
        cleanup_router,
    ]
    
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
    "projects_files_business_router",
    "projects_files_operational_router",
    "projects_files_health_router",
    "billing_admin_router",
    "billing_operation_router",
]
