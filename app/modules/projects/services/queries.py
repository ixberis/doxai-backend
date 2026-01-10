# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/services/queries.py

Capa de aplicación (lecturas/consultas) del módulo Projects.
Orquesta ProjectQueryFacade y NO reimplementa queries complejas.
Ahora async para compatibilidad con AsyncSession.

Autor: Ixchel Beristain
Fecha: 2025-10-26 (async 2025-12-27)
Actualizado: 2026-01-09 - SSOT: aceptar auth_user_id (UUID) + fallback legacy user_email
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

# IMPORTANTE:
# Import directo para evitar side-effects/ciclos via facades/__init__.py
from app.modules.projects.facades.project_query_facade import ProjectQueryFacade

from app.modules.projects.enums import ProjectState, ProjectStatus
from app.modules.projects.enums.project_action_type_enum import ProjectActionType
from app.modules.projects.enums.project_file_event_enum import ProjectFileEvent


class ProjectsQueryService:
    """Consultas de proyectos, archivos y auditoría. Async."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.facade = ProjectQueryFacade(db)

    # ---- Proyectos ----
    async def get_project_by_id(self, project_id: int):
        return await self.facade.get_by_id(project_id)

    async def get_project_by_slug(self, slug: str):
        return await self.facade.get_by_slug(slug)

    async def list_projects_by_user(
        self,
        user_email: str,
        *,
        state: Optional[ProjectState] = None,
        status: Optional[ProjectStatus] = None,
        limit: int = 50,
        offset: int = 0,
        include_total: bool = False,
    ):
        return await self.facade.list_by_user(
            user_email=user_email,
            state=state,
            status=status,
            limit=limit,
            offset=offset,
            include_total=include_total,
        )

    async def list_ready_projects(
        self,
        *,
        user_email: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        include_total: bool = False,
    ):
        return await self.facade.list_ready_projects(
            user_email=user_email,
            limit=limit,
            offset=offset,
            include_total=include_total,
        )

    async def list_active_projects(
        self,
        *,
        auth_user_id: Optional[UUID] = None,
        user_email: Optional[str] = None,
        order_by: str = "updated_at",
        asc: bool = False,
        limit: int = 50,
        offset: int = 0,
        include_total: bool = False,
    ):
        """
        Lista proyectos activos (state != ARCHIVED) con ordenamiento.

        BD 2.0 SSOT:
          - auth_user_id (UUID) preferido.
        Legacy fallback:
          - user_email (solo si auth_user_id no está disponible).
        """
        return await self.facade.list_active_projects(
            auth_user_id=auth_user_id,
            user_email=user_email,
            order_by=order_by,
            asc=asc,
            limit=limit,
            offset=offset,
            include_total=include_total,
        )

    async def list_closed_projects(
        self,
        *,
        auth_user_id: Optional[UUID] = None,
        user_email: Optional[str] = None,
        order_by: str = "updated_at",
        asc: bool = False,
        limit: int = 50,
        offset: int = 0,
        include_total: bool = False,
    ):
        """
        Lista proyectos cerrados/archivados (state == ARCHIVED) con ordenamiento.

        BD 2.0 SSOT:
          - auth_user_id (UUID) preferido.
        Legacy fallback:
          - user_email (solo si auth_user_id no está disponible).
        """
        return await self.facade.list_closed_projects(
            auth_user_id=auth_user_id,
            user_email=user_email,
            order_by=order_by,
            asc=asc,
            limit=limit,
            offset=offset,
            include_total=include_total,
        )

    # ---- Archivos ----
    async def list_files(
        self,
        project_id: UUID,
        *,
        limit: int = 100,
        offset: int = 0,
        include_total: bool = False,
    ):
        return await self.facade.list_files(
            project_id,
            limit=limit,
            offset=offset,
            include_total=include_total,
        )

    async def get_file_by_id(self, file_id: UUID):
        return await self.facade.get_file_by_id(file_id)

    async def count_files_by_project(self, project_id: UUID) -> int:
        return await self.facade.count_files_by_project(project_id)

    # ---- Auditoría ----
    async def list_actions(
        self,
        project_id: UUID,
        *,
        action_type: Optional[ProjectActionType] = None,
        limit: int = 100,
        offset: int = 0,
    ):
        return await self.facade.list_actions(
            project_id,
            action_type=action_type,
            limit=limit,
            offset=offset,
        )

    async def list_file_events(
        self,
        project_id: UUID,
        *,
        file_id: Optional[UUID] = None,
        event_type: Optional[ProjectFileEvent] = None,
        limit: int = 100,
        offset: int = 0,
    ):
        return await self.facade.list_file_events(
            project_id,
            file_id=file_id,
            event_type=event_type,
            limit=limit,
            offset=offset,
        )

    async def list_file_events_seek(
        self,
        project_id: UUID,
        *,
        after_created_at,
        after_id: UUID,
        event_type: Optional[ProjectFileEvent] = None,
        limit: int = 100,
    ):
        """Cursor-based pagination para eventos de archivos."""
        return await self.facade.list_file_events_seek(
            project_id,
            after_created_at=after_created_at,
            after_id=after_id,
            event_type=event_type,
            limit=limit,
        )


# Fin del archivo backend/app/modules/projects/services/queries.py


