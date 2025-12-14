
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/services/commands.py

Capa de aplicación (comandos/mutaciones) del módulo Projects.
Orquesta ProjectFacade y NO reimplementa reglas de dominio.
"""
from __future__ import annotations
from uuid import UUID
from typing import Optional
from sqlalchemy.orm import Session

from app.modules.projects.facades import ProjectFacade
from app.modules.projects.enums import ProjectState, ProjectStatus


class ProjectsCommandService:
    """Comandos: crear, actualizar, cambiar status/state, archivar, eliminar."""

    def __init__(self, db: Session):
        self.db = db
        self.facade = ProjectFacade(db)

    # ---- Crear / actualizar ----
    def create_project(
        self,
        *,
        user_id: UUID,
        user_email: str,
        project_name: str,
        project_slug: str,
        project_description: Optional[str] = None,
    ):
        return self.facade.create(
            user_id=user_id,
            user_email=user_email,
            project_name=project_name,
            project_slug=project_slug,
            project_description=project_description,
        )

    def update_project(
        self,
        project_id: UUID,
        *,
        user_id: UUID,
        user_email: str,
        project_name: Optional[str] = None,
        project_description: Optional[str] = None,
    ):
        payload = {}
        if project_name is not None:
            payload["project_name"] = project_name
        if project_description is not None:
            payload["project_description"] = project_description

        return self.facade.update(
            project_id,
            user_id=user_id,
            user_email=user_email,
            **payload
        )

    # ---- Status administrativo ----
    def change_status(
        self,
        project_id: UUID,
        *,
        user_id: UUID,
        user_email: str,
        new_status: ProjectStatus,
    ):
        return self.facade.change_status(
            project_id,
            user_id=user_id,
            user_email=user_email,
            new_status=new_status,
        )

    # ---- State operativo ----
    def transition_state(
        self,
        project_id: UUID,
        *,
        user_id: UUID,
        user_email: str,
        to_state: ProjectState,
    ):
        return self.facade.transition_state(
            project_id,
            user_id=user_id,
            user_email=user_email,
            to_state=to_state,
        )

    def archive(self, project_id: UUID, *, user_id: UUID, user_email: str):
        return self.facade.archive(
            project_id,
            user_id=user_id,
            user_email=user_email,
        )

    def delete(self, project_id: UUID, *, user_id: UUID, user_email: str) -> bool:
        return self.facade.delete(
            project_id,
            user_id=user_id,
            user_email=user_email,
        )

    # ---- Operaciones de archivos ----
    def add_file(
        self,
        *,
        project_id: UUID,
        user_id: UUID,
        user_email: str,
        path: str,
        filename: str,
        mime_type: Optional[str] = None,
        size_bytes: Optional[int] = None,
        checksum: Optional[str] = None,
    ):
        """Agrega un archivo al proyecto."""
        from app.modules.projects.facades import ProjectFileFacade
        file_facade = ProjectFileFacade(self.db)
        return file_facade.add_file(
            project_id=project_id,
            user_id=user_id,
            user_email=user_email,
            path=path,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            checksum=checksum,
        )

    def validate_file(self, *, file_id: UUID, user_id: UUID, user_email: str):
        """Marca un archivo como validado."""
        from app.modules.projects.facades import ProjectFileFacade
        file_facade = ProjectFileFacade(self.db)
        return file_facade.mark_validated(
            file_id=file_id,
            user_id=user_id,
            user_email=user_email,
        )

    def move_file(self, *, file_id: UUID, user_id: UUID, user_email: str, new_path: str):
        """Mueve un archivo a una nueva ruta."""
        from app.modules.projects.facades import ProjectFileFacade
        file_facade = ProjectFileFacade(self.db)
        return file_facade.move_file(
            file_id=file_id,
            user_id=user_id,
            user_email=user_email,
            new_path=new_path,
        )

    def delete_file(self, *, file_id: UUID, user_id: UUID, user_email: str) -> bool:
        """Elimina un archivo del proyecto."""
        from app.modules.projects.facades import ProjectFileFacade
        file_facade = ProjectFileFacade(self.db)
        return file_facade.delete_file(
            file_id=file_id,
            user_id=user_id,
            user_email=user_email,
        )
# Fin del archivo backend/app/modules/projects/services/commands.py