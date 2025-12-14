
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/services/__init__.py

Servicios de aplicación del módulo Projects.

Capa de orquestación (application layer) sobre las facades:
- ProjectsCommandService : comandos/mutaciones (create/update/state/status/files)
- ProjectsQueryService   : lecturas/consultas (projects, files, auditoría)

Servicios in-memory para tests de rutas:
- InMemoryProjectsQueryService
- InMemoryProjectsCommandService

Autor: Ixchel Beristáin
Fecha: 2025-11-21 (ajustado para Projects v2)
"""

from .commands import ProjectsCommandService
from .queries import ProjectsQueryService
from .inmemory import InMemoryProjectsQueryService, InMemoryProjectsCommandService

__all__ = [
    # Application services
    "ProjectsCommandService",
    "ProjectsQueryService",
    # In-memory services for tests
    "InMemoryProjectsQueryService",
    "InMemoryProjectsCommandService",
]

# Fin del archivo backend/app/modules/projects/services/__init__.py
