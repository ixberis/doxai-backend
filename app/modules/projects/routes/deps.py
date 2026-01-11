# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/routes/deps.py

Dependencias inyectables para los servicios reales de Projects.
Tests pueden overridear estas dependencias con stubs InMemory.

Autor: Ixchel Beristain
Ajustado: 2026-01-11 - Instrumentación timing para factories (gap analysis)
"""

import time
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.shared.observability.dep_timing import record_dep_timing
from app.modules.projects.services import (
    ProjectsCommandService,
    ProjectsQueryService,
)


def get_projects_command_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ProjectsCommandService:
    """
    Devuelve el servicio real para comandos de Projects.
    Tests pueden overridearlo con InMemoryProjectsCommandService.
    
    Timing: records dep_factory.projects_command_service_ms
    """
    start = time.perf_counter()
    svc = ProjectsCommandService(db)
    elapsed_ms = (time.perf_counter() - start) * 1000
    record_dep_timing(request, "dep_factory.projects_command_service_ms", elapsed_ms)
    return svc


def get_projects_query_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ProjectsQueryService:
    """
    Devuelve el servicio real para consultas de Projects.
    Tests pueden overridearlo con InMemoryProjectsQueryService.
    
    Timing: records dep_factory.projects_query_service_ms
    """
    start = time.perf_counter()
    svc = ProjectsQueryService(db)
    elapsed_ms = (time.perf_counter() - start) * 1000
    record_dep_timing(request, "dep_factory.projects_query_service_ms", elapsed_ms)
    return svc


# Fin del archivo backend/app/modules/projects/routes/deps.py
