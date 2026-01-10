# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/project_query_facade.py

Facade público para consultas y listados de proyectos, archivos y auditoría.
Ahora async para compatibilidad con AsyncSession.

Autor: Ixchel Beristain
Fecha: 2025-10-26 (async 2025-12-27)
Actualizado: 2026-01-09 - SSOT: aceptar auth_user_id (UUID) + fallback legacy user_email
Actualizado: 2026-01-09 - Normalización defensiva de rows: evitar tuples/listas (Project, extra)
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Tuple, Sequence, Any
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

    MAX_LIMIT = queries.projects.MAX_LIMIT

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def _strip_project_row(self, row: Any) -> Any:
        """
        Normaliza filas devueltas por queries.* cuando vienen como tuplas/listas.

        Casos comunes que rompían Pydantic en routes:
        - (Project, extra)  -> Project
        - ({...project...}, {...extra...}) -> {...project...}
        - SQLAlchemy Row con _mapping que incluye Project u otro payload adicional

        Regresa el "project payload" (primer componente) si detecta composición.
        """
        # Caso: tuple/list (project, extra)
        if isinstance(row, (list, tuple)) and len(row) >= 1:
            # Si es exactamente 2 (el caso reportado), tomamos el primero.
            if len(row) == 2:
                return row[0]
            # Si es una lista de dicts/objs (más de 2), no adivinamos:
            # regresamos tal cual y dejamos que capas superiores manejen/logueen.
            return row

        # Caso: SQLAlchemy Row / RowMapping
        mapping = getattr(row, "_mapping", None)
        if mapping is not None:
            # Si el query seleccionó entidad Project explícitamente, suele venir como key Project o 'Project'
            if Project in mapping:
                return mapping[Project]
            if "Project" in mapping:
                return mapping["Project"]
            if "project" in mapping:
                return mapping["project"]

            # Si hay exactamente dos valores y uno parece Project, tomar ese
            try:
                values = list(mapping.values())
                if len(values) == 2:
                    if isinstance(values[0], Project):
                        return values[0]
                    if isinstance(values[1], Project):
                        return values[1]
                # fallback: si el primer valor es dict/Project, preferirlo
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

        # Si al menos un elemento es tuple/list len==2, normalizamos todos
        if any(isinstance(x, (list, tuple)) and len(x) == 2 for x in items):
            return [self._strip_project_row(x) for x in items]

        # Si viene como Row con _mapping multi-columna, también normalizamos
        if any(getattr(x, "_mapping", None) is not None for x in items):
            return [self._strip_project_row(x) for x in items]

        return items

    # ===== CONSULTAS DE PROYECTOS =====

    async def get_by_id(self, project_id: int) -> Optional[Project]:
        return await queries.get_project_by_id(self.db, project_id)

    async def get_by_slug(self, slug: str) -> Optional[Project]:
        return await queries.get_project_by_slug(self.db, slug)

    async def list_by_user(
        self,
        user_email: Optional[str] = None,
        *,
        user_id=None,
        state: Optional[ProjectState] = None,
        status: Optional[ProjectStatus] = None,
        limit: int = 50,
        offset: int = 0,
        include_total: bool = False,
    ) -> List[Project] | Tuple[List[Project], int]:
        """
        Lista proyectos de un usuario con filtros opcionales.

        Note:
            user_id es para compatibilidad con tests; en prod usar user_email.
        """
        if user_id is not None:
            return await queries.list_projects_by_user_id(
                db=self.db,
                user_id=user_id,
                state=state,
                status=status,
                limit=limit,
                offset=offset,
                include_total=include_total,
            )

        if user_email is not None:
            return await queries.list_projects_by_user(
                db=self.db,
                user_email=user_email,
                state=state,
                status=status,
                limit=limit,
                offset=offset,
                include_total=include_total,
            )

        raise ValueError("Debe proporcionar user_email o user_id")

    async def list_ready_projects(
        self,
        user_email: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        include_total: bool = False,
    ) -> List[Project] | Tuple[List[Project], int]:
        return await queries.list_ready_projects(
            db=self.db,
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
    ) -> Tuple[List[Project], int]:
        if auth_user_id is None and not user_email:
            raise ValueError("Debe proporcionar auth_user_id o user_email")

        try:
            result = await queries.list_active_projects(
                db=self.db,
                auth_user_id=auth_user_id,
                user_email=user_email,
                order_by=order_by,
                asc=asc,
                limit=limit,
                offset=offset,
                include_total=include_total,
            )
        except TypeError:
            if not user_email:
                raise
            result = await queries.list_active_projects(
                db=self.db,
                user_email=user_email,
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

        # ✅ Normalizar items para evitar filas compuestas (project, extra)
        items = self._normalize_project_items(items)

        return items, total

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
    ) -> Tuple[List[Project], int]:
        if auth_user_id is None and not user_email:
            raise ValueError("Debe proporcionar auth_user_id o user_email")

        try:
            result = await queries.list_closed_projects(
                db=self.db,
                auth_user_id=auth_user_id,
                user_email=user_email,
                order_by=order_by,
                asc=asc,
                limit=limit,
                offset=offset,
                include_total=include_total,
            )
        except TypeError:
            if not user_email:
                raise
            result = await queries.list_closed_projects(
                db=self.db,
                user_email=user_email,
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

        # ✅ Normalizar items para evitar filas compuestas (project, extra)
        items = self._normalize_project_items(items)

        return items, total

    async def count_projects_by_user(
        self,
        user_email: str,
        state: Optional[ProjectState] = None,
        status: Optional[ProjectStatus] = None,
    ) -> int:
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
        return await queries.list_files(
            db=self.db,
            project_id=project_id,
            limit=limit,
            offset=offset,
            include_total=include_total,
        )

    async def get_file_by_id(self, file_id: UUID) -> Optional[ProjectFile]:
        return await queries.get_file_by_id(self.db, file_id)

    async def count_files_by_project(self, project_id: UUID) -> int:
        return await queries.count_files_by_project(self.db, project_id)

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
# Fin del archivo backend/app/modules/projects/facades/project_query_facade.py


