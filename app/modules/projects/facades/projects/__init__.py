# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/projects/__init__.py

Re-exporta operaciones de proyectos (CRUD + estado).

Autor: Ixchel Beristain
Fecha: 2025-10-26
"""

from .crud import (
    create,
    update,
    delete,
    ALLOWED_UPDATE_FIELDS,
)
from .state import (
    change_status,
    transition_state,
    archive,
    close_project,
)

__all__ = [
    # CRUD
    "create",
    "update",
    "delete",
    "ALLOWED_UPDATE_FIELDS",
    
    # Estado
    "change_status",
    "transition_state",
    "archive",
    "close_project",
]
