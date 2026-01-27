# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/project_query_facade.py

Facade público para consultas y listados de proyectos y auditoría.
Ahora async para compatibilidad con AsyncSession.

BD 2.0 SSOT (2026-01-27):
- Todas las funciones de ownership usan auth_user_id (UUID)
- NO existe columna user_email en projects
- Eliminados métodos legacy que usaban user_email
- Eliminados métodos de files legacy (Files 2.0 es el SSOT)

Autor: Ixchel Beristain
Fecha: 2025-10-26 (async 2025-12-27)
Actualizado: 2026-01-27 - Eliminar ProjectFile legacy
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Tuple, Sequence, Any
from uuid import UUID

from sqlalchemy import tuple_, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import queries

from app.modules.projects.models.project_models import Project
from app.modules.projects.models.project_action_log_models import ProjectActionLog
from app.modules.projects.models.project_file_event_log_models import ProjectFileEventLog
from app.modules.projects.enums.project_state_enum import ProjectState
from app.modules.projects.enums.project_status_enum import ProjectStatus
from app.modules.projects.enums.project_action_type_enum import ProjectActionType
from app.modules.projects.enums.project_file_event_enum import ProjectFileEvent


class ProjectQueryFacade:
    """
    Facade público para consultas de solo lectura sobre proyectos.
    
    BD 2.0 SSOT:
    - Todas las funciones de ownership requieren auth_user_id (UUID)
    - NO hay soporte para user_email (columna no existe en BD 2.0)
    - NO hay métodos de files legacy (Files 2.0 es el SSOT)
    """

    MAX_LIMIT = queries.projects.MAX_LIMIT

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def _strip_project_row(self, row: Any) -> Any:
        """
        Normaliza filas devueltas por queries.* cuando vienen como tuplas/listas.
        """
        # Caso: tuple/list (project, extra)
        if isinstance(row, (list, tuple)) and len(row) >= 1:
            if len(row) == 2:
                return row[0]
            return row

        # Caso: SQLAlchemy Row / RowMapping
        mapping = getattr(row, "_mapping", None)
        if mapping is not None:
            if Project in mapping:
                return mapping[Project]
            if "Project" in mapping:
                return mapping["Project"]
            if "project" in mapping:
                return mapping["project"]

            try:
                values = list(mapping.values())
                if len(values) == 2:
                    if isinstance(values[0], Project):
                        return values[0]
                    if isinstance(values[1], Project):
                        return values[1]
                if values and (isinstance(values[0], (dict, Project))):
                    return values[0]
            except Exception:
                pass

        return row

    def _normalize_project_items(self, items: Any) -> Any:
        """
        Normaliza lista de items para que sea List[Project] o List[dict],
        no List[tuple/list] por fila.
        """
        if not isinstance(items, list):
            return items
        if not items:
            return items

        if any(isinstance(x, (list, tuple)) and len(x) == 2 for x in items):
            return [self._strip_project_row(x) for x in items]

        if any(getattr(x, "_mapping", None) is not None for x in items):
            return [self._strip_project_row(x) for x in items]

        return items

    # ===== CONSULTAS DE PROYECTOS =====

    async def get_by_id(self, project_id: UUID) -> Optional[Project]:
        return await queries.get_project_by_id(self.db, project_id)

    async def get_by_slug(self, slug: str) -> Optional[Project]:
        return await queries.get_project_by_slug(self.db, slug)

    async def list_by_auth_user_id(
        self,
        auth_user_id: UUID,
        *,
        state: Optional[ProjectState] = None,
        status: Optional[ProjectStatus] = None,
        limit: int = 50,
        offset: int = 0,
        include_total: bool = False,
    ) -> List[Project] | Tuple[List[Project], int]:
        """
        Lista proyectos de un usuario por auth_user_id (UUID SSOT).
        
        BD 2.0: Este es el ÚNICO método válido para listar por usuario.
        """
        return await queries.list_projects_by_auth_user_id(
            db=self.db,
            auth_user_id=auth_user_id,
            state=state,
            status=status,
            limit=limit,
            offset=offset,
            include_total=include_total,
        )

    async def list_ready_projects(
        self,
        auth_user_id: Optional[UUID] = None,
        limit: int = 50,
        offset: int = 0,
        include_total: bool = False,
    ) -> List[Project] | Tuple[List[Project], int]:
        """
        Lista proyectos en estado 'ready'.
        
        BD 2.0 SSOT: Filtro opcional por auth_user_id (UUID).
        """
        return await queries.list_ready_projects(
            db=self.db,
            auth_user_id=auth_user_id,
            limit=limit,
            offset=offset,
            include_total=include_total,
        )

    async def list_active_projects(
        self,
        *,
        auth_user_id: UUID,
        order_by: str = "updated_at",
        asc: bool = False,
        limit: int = 50,
        offset: int = 0,
        include_total: bool = False,
    ) -> Tuple[List[Project], int]:
        """
        Lista proyectos activos (state != ARCHIVED) de un usuario.
        
        BD 2.0 SSOT: REQUIERE auth_user_id (UUID).
        """
        result = await queries.list_active_projects(
            db=self.db,
            auth_user_id=auth_user_id,
            order_by=order_by,
            asc=asc,
            limit=limit,
            offset=offset,
            include_total=include_total,
        )

        if isinstance(result, tuple):
            items, total = result
        else:
            items = result
            total = len(items)

        items = self._normalize_project_items(items)
        return items, total

    async def list_closed_projects(
        self,
        *,
        auth_user_id: UUID,
        order_by: str = "updated_at",
        asc: bool = False,
        limit: int = 50,
        offset: int = 0,
        include_total: bool = False,
    ) -> Tuple[List[Project], int]:
        """
        Lista proyectos cerrados/archivados (state == ARCHIVED) de un usuario.
        
        BD 2.0 SSOT: REQUIERE auth_user_id (UUID).
        """
        result = await queries.list_closed_projects(
            db=self.db,
            auth_user_id=auth_user_id,
            order_by=order_by,
            asc=asc,
            limit=limit,
            offset=offset,
            include_total=include_total,
        )

        if isinstance(result, tuple):
            items, total = result
        else:
            items = result
            total = len(items)

        items = self._normalize_project_items(items)
        return items, total

    async def count_projects_by_auth_user_id(
        self,
        auth_user_id: UUID,
        state: Optional[ProjectState] = None,
        status: Optional[ProjectStatus] = None,
    ) -> int:
        """
        Cuenta proyectos de un usuario.
        
        BD 2.0 SSOT: Usa auth_user_id (UUID).
        """
        return await queries.count_projects_by_auth_user_id(
            db=self.db,
            auth_user_id=auth_user_id,
            state=state,
            status=status,
        )

    # ===== CONSULTAS DE AUDITORÍA =====

    async def list_actions(
        self,
        project_id: UUID,
        action_type: Optional[ProjectActionType] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ProjectActionLog]:
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
        query = select(ProjectFileEventLog).where(ProjectFileEventLog.project_id == project_id)

        if event_type is not None:
            query = query.where(ProjectFileEventLog.event_type == event_type)

        if after_created_at is not None and after_id is not None:
            query = query.where(
                tuple_(ProjectFileEventLog.created_at, ProjectFileEventLog.id)
                < tuple_(after_created_at, after_id)
            )

        query = query.order_by(
            ProjectFileEventLog.created_at.desc(),
            ProjectFileEventLog.id.desc(),
        ).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())


__all__ = ["ProjectQueryFacade"]
