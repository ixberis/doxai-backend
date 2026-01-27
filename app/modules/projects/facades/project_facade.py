
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/project_facade.py

Facade público para operaciones CRUD y transiciones de estado de proyectos.
Mantiene API estable delegando a módulos internos.

Autor: Ixchel Beristain
Fecha: 28/10/2025
Actualizado: 2026-01-16 - Async-aware para AsyncSession
"""

from uuid import UUID
from typing import Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models.project_models import Project
from app.modules.projects.enums.project_state_enum import ProjectState
from app.modules.projects.enums.project_status_enum import ProjectStatus

from .audit_logger import AuditLogger
from . import projects


class ProjectFacade:
    """
    Facade público para gestión de proyectos.
    
    Mantiene API estable para compatibilidad, delegando a módulos internos
    organizados por responsabilidad (CRUD, estado).
    
    Reglas de dominio implementadas:
    1. Validación de transiciones de estado
    2. Seteo de ready_at/archived_at según reglas
    3. Auditoría automática en ProjectActionLog
    4. Slug globalmente único
    """
    
    # Re-exportar lista blanca de campos
    ALLOWED_UPDATE_FIELDS = projects.ALLOWED_UPDATE_FIELDS
    
    def __init__(self, db: Union[Session, AsyncSession]):
        """
        Inicializa el facade con una sesión de base de datos.
        
        Args:
            db: Sesión SQLAlchemy activa (Session o AsyncSession)
        """
        self.db = db
        self.audit = AuditLogger(db)
    
    async def create(
        self,
        *,
        user_id: UUID,
        user_email: str,
        project_name: str,
        project_slug: str,
        project_description: Optional[str] = None,
    ) -> Project:
        """
        Crea un nuevo proyecto.
        
        Args:
            user_id: ID del usuario propietario
            user_email: Email del usuario propietario
            project_name: Nombre del proyecto
            project_slug: Slug único del proyecto
            project_description: Descripción opcional del proyecto
            
        Returns:
            Instancia de Project creada y persistida
        """
        return await projects.create(
            db=self.db,
            audit=self.audit,
            user_id=user_id,
            user_email=user_email or "",
            name=project_name,
            slug=project_slug,
            description=project_description,
        )
    
    async def update(
        self,
        project_id: UUID,
        *,
        user_id: UUID,
        user_email: str,
        enforce_owner: bool = True,
        **changes
    ) -> Project:
        """
        Actualiza metadatos de un proyecto.
        """
        return await projects.update(
            db=self.db,
            audit=self.audit,
            project_id=project_id,
            user_id=user_id,
            user_email=user_email or "",
            enforce_owner=enforce_owner,
            **changes,
        )
    
    async def change_status(
        self,
        project_id: UUID,
        *,
        user_id: UUID,
        user_email: str,
        new_status: ProjectStatus,
        enforce_owner: bool = True
    ) -> Project:
        """
        Cambia el status administrativo del proyecto.
        """
        return await projects.change_status(
            db=self.db,
            audit=self.audit,
            project_id=project_id,
            user_id=user_id,
            user_email=user_email or "",
            new_status=new_status,
            enforce_owner=enforce_owner,
        )
    
    async def transition_state(
        self,
        project_id: UUID,
        *,
        user_id: UUID,
        user_email: str,
        to_state: ProjectState,
        enforce_owner: bool = True
    ) -> Project:
        """
        Transiciona el estado técnico del proyecto.
        """
        return await projects.transition_state(
            db=self.db,
            audit=self.audit,
            project_id=project_id,
            user_id=user_id,
            user_email=user_email or "",
            to_state=to_state,
            enforce_owner=enforce_owner,
        )
    
    async def archive(
        self,
        project_id: UUID,
        *,
        user_id: UUID,
        user_email: str,
        enforce_owner: bool = True
    ) -> Project:
        """
        Archiva un proyecto (soft delete).
        """
        return await projects.archive(
            db=self.db,
            audit=self.audit,
            project_id=project_id,
            user_id=user_id,
            user_email=user_email or "",
            enforce_owner=enforce_owner,
        )
    
    async def delete(
        self,
        project_id: UUID,
        *,
        user_id: UUID,
        user_email: str,
        enforce_owner: bool = True
    ) -> bool:
        """
        Elimina un proyecto (hard delete).
        """
        return await projects.delete(
            db=self.db,
            audit=self.audit,
            project_id=project_id,
            user_id=user_id,
            user_email=user_email or "",
            enforce_owner=enforce_owner,
        )
    
    async def close_project(
        self,
        project_id: UUID,
        *,
        user_id: UUID,
        user_email: str,
        enforce_owner: bool = True,
        closed_reason: str = "user_closed_from_dashboard",
    ) -> Project:
        """
        Cierra un proyecto (inicia ciclo de retención).
        
        Opción B: Permite cerrar desde casi cualquier project_state
        excepto 'processing'.
        
        Efectos:
        - status cambia a 'closed'
        - Se registra en project_action_logs con action_details='project_closed'
        
        Args:
            closed_reason: Razón del cierre para auditoría.
        """
        return await projects.close_project(
            db=self.db,
            audit=self.audit,
            project_id=project_id,
            user_id=user_id,
            user_email=user_email or "",
            enforce_owner=enforce_owner,
            closed_reason=closed_reason,
        )

    async def hard_delete_closed_project(
        self,
        project_id: UUID,
        *,
        user_id: UUID,
        enforce_owner: bool = True
    ) -> bool:
        """
        Elimina completamente un proyecto cerrado (hard delete).
        
        RFC-FILES-RETENTION-001: Solo disponible para proyectos cerrados.
        """
        return await projects.hard_delete_closed_project(
            db=self.db,
            audit=self.audit,
            project_id=project_id,
            user_id=user_id,
            enforce_owner=enforce_owner,
        )


__all__ = ["ProjectFacade"]
# Fin del archivo backend/app/modules/projects/facades/project_facade.py
