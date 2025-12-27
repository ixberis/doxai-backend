# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/queries/__init__.py

Re-exporta consultas de proyectos, archivos y auditoría.

Autor: Ixchel Beristain
Fecha: 2025-10-26
"""

from .projects import (
    get_by_id as get_project_by_id,
    get_by_slug as get_project_by_slug,
    list_by_user as list_projects_by_user,
    list_ready_projects,
    list_active_projects,
    list_closed_projects,
    count_projects_by_user,
)
from .files import (
    list_files,
    get_file_by_id,
    count_files_by_project,
)
from .audit import (
    list_actions,
    list_file_events,
)

__all__ = [
    # Projects
    "get_project_by_id",
    "get_project_by_slug",
    "list_projects_by_user",
    "list_ready_projects",
    "list_active_projects",
    "list_closed_projects",
    "count_projects_by_user",
    
    # Files
    "list_files",
    "get_file_by_id",
    "count_files_by_project",
    
    # Audit
    "list_actions",
    "list_file_events",
]
