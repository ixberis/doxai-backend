
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/routes/deps.py

Dependencias inyectables para los servicios reales de Projects.
Tests pueden overridear estas dependencias con stubs InMemory.

Autor: Ixchel Beristain
Ajustado: Projects v2 async (2025-12-27)
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.modules.projects.services import (
    ProjectsCommandService,
    ProjectsQueryService,
)


async def get_projects_command_service(
    db: AsyncSession = Depends(get_db),
) -> ProjectsCommandService:
    """
    Devuelve el servicio real para comandos de Projects.
    Tests pueden overridearlo con InMemoryProjectsCommandService.
    """
    return ProjectsCommandService(db)


async def get_projects_query_service(
    db: AsyncSession = Depends(get_db),
) -> ProjectsQueryService:
    """
    Devuelve el servicio real para consultas de Projects.
    Tests pueden overridearlo con InMemoryProjectsQueryService.
    """
    return ProjectsQueryService(db)
# Fin del archivo backend\app\modules\projects\routes\deps.py
