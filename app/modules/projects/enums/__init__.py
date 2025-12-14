
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/enums/__init__.py

Export central de enums del módulo de proyectos.
Incluye registro PG_ENUM_REGISTRY para acceso centralizado a tipos PostgreSQL.

DEFAULT_SCHEMA: Define el schema por defecto para tipos ENUM en PostgreSQL.
PG_ENUM_REGISTRY: Cada valor es un callable que devuelve el tipo SQLAlchemy.

Autor: Ixchel Beristáin
Fecha: 2025-10-28
"""

# Default schema for all project enums
DEFAULT_SCHEMA = "public"

# ===== PROJECT ENUMS =====
from .project_action_type_enum import (
    ProjectActionType,
    as_pg_enum as project_action_type_pg_enum,
)
from .project_file_event_enum import (
    ProjectFileEvent,
    as_pg_enum as project_file_event_pg_enum,
)
from .project_state_enum import (
    ProjectState,
    as_pg_enum as project_state_pg_enum,
)
from .project_status_enum import (
    ProjectStatus,
    as_pg_enum as project_status_pg_enum,
)
from .project_state_transitions import (
    VALID_STATE_TRANSITIONS,
    ProjectStateTransitions,  # alias retrocompatible
    is_valid_state_transition,
    get_allowed_transitions,
    validate_state_transition,
)

# ===== DEFAULTS CENTRALIZADOS =====
DEFAULT_PROJECT_STATE = ProjectState.created
DEFAULT_PROJECT_STATUS = ProjectStatus.in_process

# ===== REGISTRY PARA ACCESO CENTRALIZADO =====
PG_ENUM_REGISTRY = {
    "project_action_type_enum": project_action_type_pg_enum,
    "project_file_event_enum": project_file_event_pg_enum,
    "project_state_enum": project_state_pg_enum,
    "project_status_enum": project_status_pg_enum,
}

__all__ = [
    # Enums
    "ProjectActionType",
    "ProjectFileEvent",
    "ProjectState",
    "ProjectStatus",
    # Registry and config
    "PG_ENUM_REGISTRY",
    "DEFAULT_SCHEMA",
    # Defaults
    "DEFAULT_PROJECT_STATE",
    "DEFAULT_PROJECT_STATUS",
    # State transitions
    "VALID_STATE_TRANSITIONS",
    "ProjectStateTransitions",
    "is_valid_state_transition",
    "get_allowed_transitions",
    "validate_state_transition",
]

# Fin del archivo backend\app\modules\projects\enums\__init__.py