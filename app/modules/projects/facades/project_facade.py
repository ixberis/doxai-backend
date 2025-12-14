
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/project_facade.py

Facade público para operaciones CRUD y transiciones de estado de proyectos.
Mantiene API estable delegando a módulos internos.

Autor: Ixchel Beristain
Fecha: 28/10/2025
"""

from uuid import UUID
from typing import Optional
from sqlalchemy.orm import Session

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
    
    def __init__(self, db: Session):
        """
        Inicializa el facade con una sesión de base de datos.
        
        Args:
            db: Sesión SQLAlchemy activa
        """
        self.db = db
        self.audit = AuditLogger(db)
    
    def create(
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
        return projects.create(
            db=self.db,
            audit=self.audit,
            user_id=user_id,
            user_email=user_email,
            name=project_name,
            slug=project_slug,
            description=project_description,
        )
    
    def update(
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
        return projects.update(
            db=self.db,
            audit=self.audit,
            project_id=project_id,
            user_id=user_id,
            user_email=user_email,
            enforce_owner=enforce_owner,
            **changes,
        )
    
    def change_status(
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
        return projects.change_status(
            db=self.db,
            audit=self.audit,
            project_id=project_id,
            user_id=user_id,
            user_email=user_email,
            new_status=new_status,
            enforce_owner=enforce_owner,
        )
    
    def transition_state(
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
        return projects.transition_state(
            db=self.db,
            audit=self.audit,
            project_id=project_id,
            user_id=user_id,
            user_email=user_email,
            to_state=to_state,
            enforce_owner=enforce_owner,
        )
    
    def archive(
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
        return projects.archive(
            db=self.db,
            audit=self.audit,
            project_id=project_id,
            user_id=user_id,
            user_email=user_email,
            enforce_owner=enforce_owner,
        )
    
    def delete(
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
        return projects.delete(
            db=self.db,
            audit=self.audit,
            project_id=project_id,
            user_id=user_id,
            user_email=user_email,
            enforce_owner=enforce_owner,
        )


__all__ = ["ProjectFacade"]
# Fin del archivo backend/app/modules/projects/facades/project_facade.py
