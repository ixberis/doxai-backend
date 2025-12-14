
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/services/queries.py

Capa de aplicación (lecturas/consultas) del módulo Projects.
Orquesta ProjectQueryFacade y NO reimplementa queries complejas.
"""
from __future__ import annotations
from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Session

from app.modules.projects.facades import ProjectQueryFacade
from app.modules.projects.enums import ProjectState, ProjectStatus
from app.modules.projects.enums.project_action_type_enum import ProjectActionType
from app.modules.projects.enums.project_file_event_enum import ProjectFileEvent


class ProjectsQueryService:
    """Consultas de proyectos, archivos y auditoría."""

    def __init__(self, db: Session):
        self.db = db
        self.facade = ProjectQueryFacade(db)

    # ---- Proyectos ----
    def get_project_by_id(self, project_id: UUID):
        return self.facade.get_by_id(project_id)

    def get_project_by_slug(self, slug: str):
        return self.facade.get_by_slug(slug)

    def list_projects_by_user(
        self,
        user_id: UUID,
        *,
        state: Optional[ProjectState] = None,
        status: Optional[ProjectStatus] = None,
        limit: int = 50,
        offset: int = 0,
        include_total: bool = False,
    ):
        return self.facade.list_by_user(
            user_id=user_id,
            state=state,
            status=status,
            limit=limit,
            offset=offset,
            include_total=include_total,
        )

    def list_ready_projects(
        self,
        *,
        user_id: Optional[UUID] = None,
        limit: int = 50,
        offset: int = 0,
        include_total: bool = False,
    ):
        return self.facade.list_ready_projects(
            user_id=user_id,
            limit=limit,
            offset=offset,
            include_total=include_total,
        )

    # ---- Archivos ----
    def list_files(self, project_id: UUID, *, limit: int = 100, offset: int = 0, include_total: bool = False):
        return self.facade.list_files(project_id, limit=limit, offset=offset, include_total=include_total)

    def get_file_by_id(self, file_id: UUID):
        return self.facade.get_file_by_id(file_id)

    def count_files_by_project(self, project_id: UUID) -> int:
        return self.facade.count_files_by_project(project_id)

    # ---- Auditoría ----
    def list_actions(self, project_id: UUID, *, action_type: Optional[ProjectActionType] = None, limit: int = 100, offset: int = 0):
        return self.facade.list_actions(project_id, action_type=action_type, limit=limit, offset=offset)

    def list_file_events(
        self,
        project_id: UUID,
        *,
        file_id: Optional[UUID] = None,
        event_type: Optional[ProjectFileEvent] = None,
        limit: int = 100,
        offset: int = 0,
    ):
        return self.facade.list_file_events(project_id, file_id=file_id, event_type=event_type, limit=limit, offset=offset)
# Fin del archivo backend/app/modules/projects/services/queries.py