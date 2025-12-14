
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/models/__init__.py

Barrel de modelos del módulo Projects.
Expone los modelos principales de dominio y mantiene alias de compatibilidad.

Modelos:
- Project               : Proyecto de usuario (aggregate root del módulo).
- ProjectFile           : Archivos asociados a proyectos.
- ProjectActionLog      : Bitácora de acciones sobre proyectos.
- ProjectFileEventLog   : Bitácora de eventos sobre archivos de proyecto.

Alias de compatibilidad:
- ProjectActivity → ProjectActionLog (para código legado que aún lo importa).

Autor: Ixchel Beristáin
Fecha: 29/10/2025 (ajustado para Projects v2)
"""

from .project_models import Project
from .project_file_models import ProjectFile
from .project_action_log_models import ProjectActionLog
from .project_file_event_log_models import ProjectFileEventLog

# Alias de compatibilidad: algunos servicios aún importan ProjectActivity
ProjectActivity = ProjectActionLog

__all__ = [
    "Project",
    "ProjectFile",
    "ProjectActionLog",
    "ProjectFileEventLog",
    "ProjectActivity",  # alias para compatibilidad
]

# Fin del archivo backend\app\modules\projects\models\__init__.py
