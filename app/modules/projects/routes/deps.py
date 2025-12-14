
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/routes/deps.py

Dependencias inyectables para los servicios reales de Projects.
Tests pueden overridear estas dependencias con stubs InMemory.

Autor: Ixchel Beristain
Ajustado: Projects v2 (2025-11-21)
"""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.shared.database.database import get_db
from app.modules.projects.services import (
    ProjectsCommandService,
    ProjectsQueryService,
)


def get_projects_command_service(
    db: Session = Depends(get_db),
) -> ProjectsCommandService:
    """
    Devuelve el servicio real para comandos de Projects.
    Tests pueden overridearlo con InMemoryProjectsCommandService.
    """
    return ProjectsCommandService(db)


def get_projects_query_service(
    db: Session = Depends(get_db),
) -> ProjectsQueryService:
    """
    Devuelve el servicio real para consultas de Projects.
    Tests pueden overridearlo con InMemoryProjectsQueryService.
    """
    return ProjectsQueryService(db)
# Fin del archivo backend\app\modules\projects\routes\deps.py
