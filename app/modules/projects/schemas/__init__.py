
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/schemas/__init__.py

Schemas Pydantic del módulo de proyectos.
Alineados con ProjectState/ProjectStatus y facades.

Autor: DoxAI / Ajustes Projects v2
Fecha: 2025-11-21
"""

from .project_schemas import (
    ProjectCreateIn,
    ProjectUpdateIn,
    ProjectRead,
    ProjectResponse,
    ProjectListResponse,
)

from .project_action_log_schemas import (
    ProjectActionLogCreateIn,
    ProjectActivityCreate,  # Alias legacy
    ProjectActionLogRead,
    ProjectActionLogQuery,
    ProjectActionLogListResponse,
)

from .project_file_event_log_schemas import (
    ProjectFileEventLogRead,
    ProjectFileEventLogLite,
    ProjectFileEventLogQuery,
    ProjectFileEventLogListResponse,
    ProjectFileEventLogListLiteResponse,
)

from .project_query_schemas import (
    ProjectListByUserQuery,
    ProjectListReadyQuery,
    ProjectListFilesQuery,
)

# Aliases legacy para compatibilidad con tests antiguos
ProjectCreate = ProjectCreateIn
ProjectActivityRead = ProjectActionLogRead

__all__ = [
    # Project schemas
    "ProjectCreateIn",
    "ProjectUpdateIn",
    "ProjectRead",
    "ProjectResponse",
    "ProjectListResponse",
    "ProjectCreate",  # Alias legacy

    # Action log schemas
    "ProjectActionLogCreateIn",
    "ProjectActivityCreate",  # Alias legacy
    "ProjectActionLogRead",
    "ProjectActivityRead",  # Alias legacy
    "ProjectActionLogQuery",
    "ProjectActionLogListResponse",

    # File event log schemas
    "ProjectFileEventLogRead",
    "ProjectFileEventLogLite",
    "ProjectFileEventLogQuery",
    "ProjectFileEventLogListResponse",
    "ProjectFileEventLogListLiteResponse",

    # Query schemas
    "ProjectListByUserQuery",
    "ProjectListReadyQuery",
    "ProjectListFilesQuery",
]

# Fin del archivo backend/app/modules/projects/schemas/__init__.py

