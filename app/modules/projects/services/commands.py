# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/services/commands.py

Capa de aplicación (comandos/mutaciones) del módulo Projects.
Orquesta ProjectFacade y NO reimplementa reglas de dominio.

BD 2.0 SSOT (2026-01-27):
- auth_user_id (UUID): SSOT de ownership para todos los comandos
- Eliminados métodos de files legacy (Files 2.0 es el SSOT de archivos)
- NO existe tabla project_files en BD 2.0

Autor: Ixchel Beristain
Actualizado: 2026-01-27 - Eliminar métodos de files legacy
"""
from __future__ import annotations
from uuid import UUID
from typing import Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.facades import ProjectFacade
from app.modules.projects.enums import ProjectState, ProjectStatus


class ProjectsCommandService:
    """
    Comandos: crear, actualizar, cambiar status/state, archivar, eliminar.
    
    BD 2.0 SSOT: 
    - Todos los comandos usan auth_user_id (UUID) para ownership.
    - Para operaciones de archivos, usar el módulo Files 2.0.
    """

    def __init__(self, db: Union[Session, AsyncSession]):
        self.db = db
        self.facade = ProjectFacade(db)

    # ---- Crear / actualizar ----
    async def create_project(
        self,
        *,
        auth_user_id: UUID,
        user_email: Optional[str],  # Solo para auditoría, NO se almacena en projects
        project_name: str,
        project_slug: str,
        project_description: Optional[str] = None,
    ):
        """BD 2.0: auth_user_id es el SSOT de ownership."""
        return await self.facade.create(
            user_id=auth_user_id,  # Facade espera user_id, se mapea a auth_user_id
            user_email=user_email or "",
            project_name=project_name,
            project_slug=project_slug,
            project_description=project_description,
        )

    async def update_project(
        self,
        project_id: UUID,
        *,
        auth_user_id: UUID,
        user_email: Optional[str],
        project_name: Optional[str] = None,
        project_description: Optional[str] = None,
    ):
        """BD 2.0: auth_user_id es el SSOT de ownership."""
        payload = {}
        if project_name is not None:
            payload["project_name"] = project_name
        if project_description is not None:
            payload["project_description"] = project_description

        return await self.facade.update(
            project_id,
            user_id=auth_user_id,
            user_email=user_email or "",
            **payload
        )

    # ---- Status administrativo ----
    async def change_status(
        self,
        project_id: UUID,
        *,
        auth_user_id: UUID,
        user_email: Optional[str],
        new_status: ProjectStatus,
    ):
        return await self.facade.change_status(
            project_id,
            user_id=auth_user_id,
            user_email=user_email or "",
            new_status=new_status,
        )

    # ---- State operativo ----
    async def transition_state(
        self,
        project_id: UUID,
        *,
        auth_user_id: UUID,
        user_email: Optional[str],
        to_state: ProjectState,
    ):
        return await self.facade.transition_state(
            project_id,
            user_id=auth_user_id,
            user_email=user_email or "",
            to_state=to_state,
        )

    async def archive(self, project_id: UUID, *, auth_user_id: UUID, user_email: Optional[str]):
        return await self.facade.archive(
            project_id,
            user_id=auth_user_id,
            user_email=user_email or "",
        )

    async def close_project(
        self,
        project_id: UUID,
        *,
        auth_user_id: UUID,
        user_email: Optional[str],
        closed_reason: str = "user_closed_from_dashboard",
    ):
        """
        Cierra un proyecto (inicia ciclo de retención).
        
        Opción B: Permite cerrar desde casi cualquier project_state.
        
        Estados permitidos:
        - created, uploading, ready, error, archived → OK
        - processing → RECHAZADO (400)
        
        BD 2.0 SSOT: usa auth_user_id para ownership.
        
        Args:
            closed_reason: Razón del cierre para auditoría.
        
        Raises:
            ProjectCloseNotAllowed: si el proyecto está en processing.
        """
        return await self.facade.close_project(
            project_id,
            user_id=auth_user_id,
            user_email=user_email or "",
            closed_reason=closed_reason,
        )

    async def delete(self, project_id: UUID, *, auth_user_id: UUID, user_email: Optional[str]) -> bool:
        return await self.facade.delete(
            project_id,
            user_id=auth_user_id,
            user_email=user_email or "",
        )

    async def hard_delete_closed_project(
        self,
        project_id: UUID,
        *,
        auth_user_id: UUID,
    ) -> bool:
        """
        Elimina completamente un proyecto cerrado (hard delete).
        
        RFC-FILES-RETENTION-001: Solo disponible para proyectos cerrados.
        
        Requisitos:
        - El proyecto debe tener status !== 'in_process'
        - El usuario debe ser propietario
        
        Efectos:
        - El proyecto desaparece del historial
        - No afecta métricas agregadas ni billing histórico
        
        BD 2.0 SSOT: usa auth_user_id para ownership.
        
        Raises:
            ProjectHardDeleteNotAllowed: si el proyecto está activo o no autorizado.
        """
        return await self.facade.hard_delete_closed_project(
            project_id,
            user_id=auth_user_id,
        )


__all__ = ["ProjectsCommandService"]
# Fin del archivo backend/app/modules/projects/services/commands.py
