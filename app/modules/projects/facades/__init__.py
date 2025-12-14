
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/__init__.py

Re-exporta facades del módulo projects para facilitar imports.
Mantiene API pública estable mientras organiza código interno por responsabilidad.

Autor: Ixchel Beristain
Fecha: 2025-10-26
"""

from .errors import (
    ProjectNotFound,
    InvalidStateTransition,
    SlugAlreadyExists,
    FileNotFound,
    PermissionDenied,
)
from .project_facade import ProjectFacade
from .project_file_facade import ProjectFileFacade
from .project_query_facade import ProjectQueryFacade

__all__ = [
    # Errors
    "ProjectNotFound",
    "InvalidStateTransition",
    "SlugAlreadyExists",
    "FileNotFound",
    "PermissionDenied",

    # Facades
    "ProjectFacade",
    "ProjectFileFacade",
    "ProjectQueryFacade",
]

# Fin del archivo backend/app/modules/projects/facades/__init__.py
