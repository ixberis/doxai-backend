# -*- coding: utf-8 -*-
"""
backend/app/modules/files/routes/__init__.py

Ensamblador de routers del módulo Files v2.

Incluye:
- activity_routes: Gestión de eventos de actividad de archivos producto
- input_files_routes: CRUD de archivos insumo
- product_files_routes: CRUD de archivos producto
- files_routes: Rutas agregadas y métricas
- project_file_activity_routes: Rutas de actividad bajo /projects/{id}/file-activity

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
Updated: 2026-01-19 - Añadir project_file_activity_routes para contrato frontend
"""

from fastapi import APIRouter

# Routers individuales
from .activity_routes import router as activity_router
from .input_files_routes import router as input_files_router
from .product_files_routes import router as product_files_router
from .files_routes import router as files_router
from .project_file_activity_routes import router as project_file_activity_router


def get_files_routers() -> list[APIRouter]:
    """
    Devuelve todos los routers del módulo Files listos para montar.
    
    Returns:
        Lista de routers de FastAPI para incluir en la aplicación principal.
    """
    return [
        activity_router,
        input_files_router,
        product_files_router,
        files_router,
        project_file_activity_router,
    ]


# Re-exportar routers individuales para compatibilidad con tests
__all__ = [
    "get_files_routers",
    "activity_router",
    "input_files_router",
    "product_files_router",
    "files_router",
    "project_file_activity_router",
]

# Fin del archivo backend/app/modules/files/routes/__init__.py
