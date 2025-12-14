
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/repositories/__init__.py

Repositorios del módulo Projects.

Agrupan acceso a base de datos para:
- Project              (proyectos)
- ProjectFile          (archivos asociados a proyectos)
- ProjectActionLog     (bitácora de acciones sobre proyectos)
- ProjectFileEventLog  (bitácora de eventos sobre archivos de proyecto)

Autor: Ixchel Beristáin
Fecha: 2025-11-21
"""

from .project_repository import (
    get_project_by_id,
    get_project_by_slug,
    list_projects_by_user,
    save_project,
    delete_project,
)
from .project_file_repository import (
    get_project_file_by_id,
    list_project_files,
    save_project_file,
    delete_project_file,
)
from .project_action_log_repository import (
    log_project_action,
    list_project_actions,
)
from .project_file_event_log_repository import (
    log_project_file_event,
    list_project_file_events,
)

__all__ = [
    # Projects
    "get_project_by_id",
    "get_project_by_slug",
    "list_projects_by_user",
    "save_project",
    "delete_project",
    # Project files
    "get_project_file_by_id",
    "list_project_files",
    "save_project_file",
    "delete_project_file",
    # Action logs
    "log_project_action",
    "list_project_actions",
    # File event logs
    "log_project_file_event",
    "list_project_file_events",
]

# Fin del archivo backend/app/modules/projects/repositories/__init__.py