
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/models/__init__.py

Barrel de modelos del módulo Projects.
Expone los modelos principales de dominio y mantiene alias de compatibilidad.

Modelos (BD 2.0 SSOT):
- Project               : Proyecto de usuario (aggregate root del módulo).
- ProjectActionLog      : Bitácora de acciones sobre proyectos.
- ProjectFileEventLog   : Bitácora de eventos sobre archivos de proyecto.

NOTA: ProjectFile (tabla project_files) fue eliminado en BD 2.0.
      Files 2.0 es el SSOT de archivos (files_base, input_files, product_files).

Alias de compatibilidad:
- ProjectActivity → ProjectActionLog (para código legado que aún lo importa).

Autor: Ixchel Beristáin
Fecha: 29/10/2025 (ajustado para Projects v2)
Actualizado: 2026-01-27 - Eliminar ProjectFile legacy (BD 2.0 SSOT)
"""

from .project_models import Project
from .project_action_log_models import ProjectActionLog
from .project_file_event_log_models import ProjectFileEventLog

# Alias de compatibilidad: algunos servicios aún importan ProjectActivity
ProjectActivity = ProjectActionLog

__all__ = [
    "Project",
    "ProjectActionLog",
    "ProjectFileEventLog",
    "ProjectActivity",  # alias para compatibilidad
]

# Fin del archivo backend/app/modules/projects/models/__init__.py
