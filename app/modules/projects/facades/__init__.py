
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/__init__.py

Re-exporta facades del módulo projects para facilitar imports.
Mantiene API pública estable mientras organiza código interno por responsabilidad.

NOTA BD 2.0: ProjectFileFacade eliminado - Files 2.0 es el SSOT de archivos.

Autor: Ixchel Beristain
Fecha: 2025-10-26
Actualizado: 2026-01-27 - Eliminar ProjectFileFacade legacy
"""

from .errors import (
    ProjectNotFound,
    InvalidStateTransition,
    SlugAlreadyExists,
    FileNotFound,
    PermissionDenied,
)
from .project_facade import ProjectFacade
from .project_query_facade import ProjectQueryFacade

__all__ = [
    # Errors
    "ProjectNotFound",
    "InvalidStateTransition",
    "SlugAlreadyExists",
    "FileNotFound",
    "PermissionDenied",

    # Facades (BD 2.0: sin ProjectFileFacade)
    "ProjectFacade",
    "ProjectQueryFacade",
]

# Fin del archivo backend/app/modules/projects/facades/__init__.py
