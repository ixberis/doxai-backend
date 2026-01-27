# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/queries/__init__.py

Re-exporta consultas de proyectos y auditoría.

BD 2.0 SSOT (2026-01-27):
- Eliminada list_projects_by_user (usaba user_email que no existe en BD 2.0)
- Eliminadas funciones de files legacy (ProjectFile no existe en BD 2.0)
- Todas las funciones de ownership usan auth_user_id (UUID)
- Files 2.0 es el SSOT de archivos (files_base, input_files, product_files)

Autor: Ixchel Beristain
Fecha: 2025-10-26
Actualizado: 2026-01-27 - Eliminar files legacy
"""

from .projects import (
    get_by_id as get_project_by_id,
    get_by_slug as get_project_by_slug,
    list_by_auth_user_id as list_projects_by_auth_user_id,
    list_by_user_id as list_projects_by_user_id,  # Alias deprecated
    list_ready_projects,
    list_active_projects,
    list_closed_projects,
    count_projects_by_auth_user_id,
    count_projects_by_user,  # Alias deprecated
)
from .audit import (
    list_actions,
    list_file_events,
)

# Submodule exports (para imports como queries.projects.MAX_LIMIT)
from . import projects

__all__ = [
    # Projects (BD 2.0 SSOT - auth_user_id)
    "get_project_by_id",
    "get_project_by_slug",
    "list_projects_by_auth_user_id",
    "list_projects_by_user_id",  # Alias deprecated → list_projects_by_auth_user_id
    "list_ready_projects",
    "list_active_projects",
    "list_closed_projects",
    "count_projects_by_auth_user_id",
    "count_projects_by_user",  # Alias deprecated → count_projects_by_auth_user_id
    
    # Submodule
    "projects",
    
    # Audit (BD 2.0: file events reference files_base, not project_files)
    "list_actions",
    "list_file_events",
]
