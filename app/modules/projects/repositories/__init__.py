
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/repositories/__init__.py

Repositorios del módulo Projects.

Agrupan acceso a base de datos para:
- Project              (proyectos)
- ProjectActionLog     (bitácora de acciones sobre proyectos)
- ProjectFileEventLog  (bitácora de eventos sobre archivos de proyecto)

NOTA BD 2.0: ProjectFile (tabla project_files) fue eliminado.
             Files 2.0 es el SSOT de archivos.

Autor: Ixchel Beristáin
Fecha: 2025-11-21
Actualizado: 2026-01-27 - Eliminar project_file_repository legacy
"""

from .project_repository import (
    get_project_by_id,
    get_project_by_slug,
    list_projects_by_user,
    save_project,
    delete_project,
)
from .project_action_log_repository import (
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
    # Action logs (NOTA: log_project_action eliminado - usar AuditLogger)
    "list_project_actions",
    # File event logs
    "log_project_file_event",
    "list_project_file_events",
]

# Fin del archivo backend/app/modules/projects/repositories/__init__.py