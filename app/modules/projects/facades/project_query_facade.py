
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/project_query_facade.py

Facade público para consultas y listados de proyectos, archivos y auditoría.
Ahora async para compatibilidad con AsyncSession.

Autor: Ixchel Beristain
Fecha: 2025-10-26 (async 2025-12-27)
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Tuple, Sequence
from uuid import UUID

from sqlalchemy import tuple_, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import queries

from app.modules.projects.models.project_models import Project
from app.modules.projects.models.project_file_models import ProjectFile
from app.modules.projects.models.project_action_log_models import ProjectActionLog
from app.modules.projects.models.project_file_event_log_models import ProjectFileEventLog
from app.modules.projects.enums.project_state_enum import ProjectState
from app.modules.projects.enums.project_status_enum import ProjectStatus
from app.modules.projects.enums.project_action_type_enum import ProjectActionType
from app.modules.projects.enums.project_file_event_enum import ProjectFileEvent


class ProjectQueryFacade:
    """
    Facade público para consultas de solo lectura sobre proyectos.
    Ahora async.
    """
    
    # Re-exportar límite máximo
    MAX_LIMIT = queries.projects.MAX_LIMIT
    
    def __init__(self, db: AsyncSession):
        """
        Inicializa el facade con una sesión de base de datos async.
        
        Args:
            db: Sesión AsyncSession SQLAlchemy activa
        """
        self.db = db
    
    # ===== CONSULTAS DE PROYECTOS =====
    
    async def get_by_id(self, project_id: int) -> Optional[Project]:
        """Obtiene un proyecto por ID."""
        return await queries.get_project_by_id(self.db, project_id)
    
    async def get_by_slug(self, slug: str) -> Optional[Project]:
        """Obtiene un proyecto por slug."""
        return await queries.get_project_by_slug(self.db, slug)
    
    async def list_by_user(
        self,
        user_email: str,
        state: Optional[ProjectState] = None,
        status: Optional[ProjectStatus] = None,
        limit: int = 50,
        offset: int = 0,
        include_total: bool = False,
    ) -> List[Project] | Tuple[List[Project], int]:
        """Lista proyectos de un usuario con filtros opcionales (por email)."""
        return await queries.list_projects_by_user(
            db=self.db,
            user_email=user_email,
            state=state,
            status=status,
            limit=limit,
            offset=offset,
            include_total=include_total,
        )
    
    async def list_ready_projects(
        self,
        user_email: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        include_total: bool = False,
    ) -> List[Project] | Tuple[List[Project], int]:
        """Lista proyectos en estado 'ready'."""
        return await queries.list_ready_projects(
            db=self.db,
            user_email=user_email,
            limit=limit,
            offset=offset,
            include_total=include_total,
        )
    
    async def list_active_projects(
        self,
        user_email: str,
        order_by: str = "updated_at",
        asc: bool = False,
        limit: int = 50,
        offset: int = 0,
        include_total: bool = False,
    ) -> Tuple[List[Project], int]:
        """Lista proyectos activos (state != ARCHIVED) con ordenamiento (por email)."""
        return await queries.list_active_projects(
            db=self.db,
            user_email=user_email,
            order_by=order_by,
            asc=asc,
            limit=limit,
            offset=offset,
            include_total=include_total,
        )
    
    async def list_closed_projects(
        self,
        user_email: str,
        order_by: str = "updated_at",
        asc: bool = False,
        limit: int = 50,
        offset: int = 0,
        include_total: bool = False,
    ) -> Tuple[List[Project], int]:
        """Lista proyectos cerrados/archivados (state == ARCHIVED) con ordenamiento (por email)."""
        return await queries.list_closed_projects(
            db=self.db,
            user_email=user_email,
            order_by=order_by,
            asc=asc,
            limit=limit,
            offset=offset,
            include_total=include_total,
        )
    
    async def count_projects_by_user(
        self,
        user_email: str,
        state: Optional[ProjectState] = None,
        status: Optional[ProjectStatus] = None,
    ) -> int:
        """Cuenta proyectos de un usuario con filtros opcionales (por email)."""
        return await queries.count_projects_by_user(
            db=self.db,
            user_email=user_email,
            state=state,
            status=status,
        )
    
    # ===== CONSULTAS DE ARCHIVOS =====
    
    async def list_files(
        self,
        project_id: UUID,
        limit: int = 100,
        offset: int = 0,
        include_total: bool = False,
    ) -> List[ProjectFile] | Tuple[List[ProjectFile], int]:
        """Lista archivos de un proyecto."""
        return await queries.list_files(
            db=self.db,
            project_id=project_id,
            limit=limit,
            offset=offset,
            include_total=include_total,
        )
    
    async def get_file_by_id(self, file_id: UUID) -> Optional[ProjectFile]:
        """Obtiene un archivo por ID."""
        return await queries.get_file_by_id(self.db, file_id)
    
    async def count_files_by_project(self, project_id: UUID) -> int:
        """Cuenta archivos de un proyecto."""
        return await queries.count_files_by_project(self.db, project_id)
    
    # ===== CONSULTAS DE AUDITORÍA =====
    
    async def list_actions(
        self,
        project_id: UUID,
        action_type: Optional[ProjectActionType] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ProjectActionLog]:
        """Lista acciones de auditoría de un proyecto."""
        return await queries.list_actions(
            db=self.db,
            project_id=project_id,
            action_type=action_type,
            limit=limit,
            offset=offset,
        )
    
    async def list_file_events(
        self,
        project_id: UUID,
        file_id: Optional[UUID] = None,
        event_type: Optional[ProjectFileEvent] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ProjectFileEventLog]:
        """Lista eventos de archivos de un proyecto."""
        return await queries.list_file_events(
            db=self.db,
            project_id=project_id,
            file_id=file_id,
            event_type=event_type,
            limit=limit,
            offset=offset,
        )

    # ===== CONSULTAS DE AUDITORÍA (cursor-based / seek) =====

    async def list_file_events_seek(
        self,
        project_id: UUID,
        *,
        after_created_at: Optional[datetime] = None,
        after_id: Optional[UUID] = None,
        event_type: Optional[ProjectFileEvent] = None,
        limit: int = 100,
    ) -> Sequence[ProjectFileEventLog]:
        """
        Lista eventos de archivos de un proyecto con paginación por cursor.
        """
        query = select(ProjectFileEventLog).where(
            ProjectFileEventLog.project_id == project_id
        )

        if event_type is not None:
            query = query.where(ProjectFileEventLog.event_type == event_type)

        # Cursor: trae registros *estrictamente menores* al cursor (orden descendente)
        if after_created_at is not None and after_id is not None:
            query = query.where(
                tuple_(
                    ProjectFileEventLog.created_at,
                    ProjectFileEventLog.id,
                )
                < tuple_(after_created_at, after_id)
            )

        query = query.order_by(
            ProjectFileEventLog.created_at.desc(),
            ProjectFileEventLog.id.desc(),
        ).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())


__all__ = ["ProjectQueryFacade"]
# Fin del archivo backend/app/modules/projects/facades/project_query_facade.py
