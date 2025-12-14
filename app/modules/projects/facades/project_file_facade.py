
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/project_file_facade.py

Facade público para operaciones sobre archivos de proyecto.
Mantiene API estable delegando a módulos internos.

Autor: Ixchel Beristain
Fecha: 2025-10-26
"""

from uuid import UUID
from typing import Optional
from sqlalchemy.orm import Session

from app.modules.projects.models.project_file_models import ProjectFile

from .audit_logger import AuditLogger
from . import files


class ProjectFileFacade:
    """
    Facade público para gestión de archivos de proyecto.
    
    Mantiene API estable para compatibilidad, delegando a módulos internos
    organizados por responsabilidad.
    
    Registra todos los eventos importantes (uploaded, validated, moved, deleted)
    en ProjectFileEventLog con snapshots de metadatos del archivo.
    """
    
    def __init__(self, db: Session):
        """
        Inicializa el facade con una sesión de base de datos.
        
        Args:
            db: Sesión SQLAlchemy activa
        """
        self.db = db
        self.audit = AuditLogger(db)
    
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
        checksum: Optional[str] = None
    ) -> ProjectFile:
        """
        Agrega un archivo a un proyecto.
        """
        return files.add_file(
            db=self.db,
            audit=self.audit,
            project_id=project_id,
            user_id=user_id,
            user_email=user_email,
            path=path,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            checksum=checksum,
        )
    
    def mark_validated(
        self,
        *,
        file_id: UUID,
        user_id: UUID,
        user_email: str
    ) -> ProjectFile:
        """
        Marca un archivo como validado.
        """
        return files.mark_validated(
            db=self.db,
            audit=self.audit,
            file_id=file_id,
            user_id=user_id,
            user_email=user_email,
        )
    
    def move_file(
        self,
        *,
        file_id: UUID,
        user_id: UUID,
        user_email: str,
        new_path: str
    ) -> ProjectFile:
        """
        Mueve un archivo a una nueva ubicación.
        """
        return files.move_file(
            db=self.db,
            audit=self.audit,
            file_id=file_id,
            user_id=user_id,
            user_email=user_email,
            new_path=new_path,
        )
    
    def delete_file(
        self,
        *,
        file_id: UUID,
        user_id: UUID,
        user_email: str
    ) -> bool:
        """
        Elimina un archivo del proyecto.
        """
        return files.delete_file(
            db=self.db,
            audit=self.audit,
            file_id=file_id,
            user_id=user_id,
            user_email=user_email,
        )


__all__ = ["ProjectFileFacade"]
# Fin del archivo backend/app/modules/projects/facades/project_file_facade.py
