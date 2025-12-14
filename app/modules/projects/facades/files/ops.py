
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/files/ops.py

Operaciones sobre archivos de proyecto: add, validate, move, delete.
Incluye registro de eventos con snapshots.

Autor: Ixchel Beristain
Fecha: 2025-10-26
Ajustado: 2025-11-21 (Projects v2: usar user_id/user_email en ProjectFile)
"""

from uuid import UUID
from typing import Optional
from sqlalchemy.orm import Session

from app.modules.projects.models.project_models import Project
from app.modules.projects.models.project_file_models import ProjectFile
from app.modules.projects.enums.project_file_event_enum import ProjectFileEvent
from app.modules.projects.facades.errors import ProjectNotFound, FileNotFound
from app.modules.projects.facades.base import commit_or_raise
from app.modules.projects.facades.audit_logger import AuditLogger


def add_file(
    db: Session,
    audit: AuditLogger,
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
    
    Reglas de negocio:
    - Valida que el proyecto exista
    - Registra evento 'uploaded' en ProjectFileEventLog
    - Almacena snapshot de metadatos del archivo
    
    Args:
        db: Sesión SQLAlchemy
        audit: Logger de auditoría
        project_id: ID del proyecto al que pertenece el archivo
        user_id: ID del usuario que sube el archivo
        user_email: Email del usuario
        path: Ruta de almacenamiento del archivo
        filename: Nombre original del archivo
        mime_type: Tipo MIME del archivo (ej. 'application/pdf')
        size_bytes: Tamaño del archivo en bytes
        checksum: Hash del archivo (ver ChecksumAlgo para algoritmos soportados)
        
    Returns:
        Instancia de ProjectFile creada y persistida
        
    Raises:
        ProjectNotFound: Si el proyecto no existe
    """
    # Validar que el proyecto existe
    project = db.get(Project, project_id)
    if not project:
        raise ProjectNotFound(project_id)
    
    def _work():
        # Crear registro de archivo (modelo v2:
        # user_id / user_email en lugar de uploaded_by)
        file = ProjectFile(
            project_id=project_id,
            path=path,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            checksum=checksum,
            user_id=user_id,
            user_email=user_email,
        )
        
        db.add(file)
        db.flush()
        
        # Registrar evento de upload
        audit.log_file_event(
            project_id=project_id,
            file_id=file.id,
            user_id=user_id,
            user_email=user_email,
            event=ProjectFileEvent.uploaded,
            file_snapshot=file,
        )
        
        return file
    
    return commit_or_raise(db, _work)


def mark_validated(
    db: Session,
    audit: AuditLogger,
    *,
    file_id: UUID,
    user_id: UUID,
    user_email: str
) -> ProjectFile:
    """
    Marca un archivo como validado.
    
    Registra evento 'validated' en auditoría.
    Útil para workflows de validación de archivos.
    
    Args:
        db: Sesión SQLAlchemy
        audit: Logger de auditoría
        file_id: ID del archivo
        user_id: ID del usuario que valida
        user_email: Email del usuario
        
    Returns:
        Archivo actualizado
        
    Raises:
        FileNotFound: Si el archivo no existe
    """
    def _work():
        file = _get_file(db, file_id)
        
        # Registrar evento de validación
        audit.log_file_event(
            project_id=file.project_id,
            file_id=file.id,
            user_id=user_id,
            user_email=user_email,
            event=ProjectFileEvent.validated,
            file_snapshot=file,
        )
        
        return file
    
    return commit_or_raise(db, _work)


def move_file(
    db: Session,
    audit: AuditLogger,
    *,
    file_id: UUID,
    user_id: UUID,
    user_email: str,
    new_path: str
) -> ProjectFile:
    """
    Mueve un archivo a una nueva ubicación.
    
    Actualiza la ruta del archivo y registra evento 'moved'.
    
    Args:
        db: Sesión SQLAlchemy
        audit: Logger de auditoría
        file_id: ID del archivo a mover
        user_id: ID del usuario que mueve el archivo
        user_email: Email del usuario
        new_path: Nueva ruta de almacenamiento
        
    Returns:
        Archivo con ruta actualizada
        
    Raises:
        FileNotFound: Si el archivo no existe
    """
    def _work():
        file = _get_file(db, file_id)
        old_path = file.path
        
        # Actualizar ruta
        file.path = new_path
        
        # Registrar evento de movimiento
        audit.log_file_event(
            project_id=file.project_id,
            file_id=file.id,
            user_id=user_id,
            user_email=user_email,
            event=ProjectFileEvent.moved,
            file_snapshot=file,
            old_path=old_path,
        )
        
        return file
    
    return commit_or_raise(db, _work)


def delete_file(
    db: Session,
    audit: AuditLogger,
    *,
    file_id: UUID,
    user_id: UUID,
    user_email: str
) -> bool:
    """
    Elimina un archivo del proyecto.
    
    Registra evento 'deleted' con snapshot de metadatos antes de eliminar.
    
    Args:
        db: Sesión SQLAlchemy
        audit: Logger de auditoría
        file_id: ID del archivo a eliminar
        user_id: ID del usuario que elimina
        user_email: Email del usuario
        
    Returns:
        True si se eliminó exitosamente
        
    Raises:
        FileNotFound: Si el archivo no existe
    """
    def _work():
        file = _get_file(db, file_id)
        
        # Registrar evento de eliminación (antes de borrar)
        audit.log_file_event(
            project_id=file.project_id,
            file_id=file.id,
            user_id=user_id,
            user_email=user_email,
            event=ProjectFileEvent.deleted,
            file_snapshot=file,
        )
        
        # Eliminar archivo
        db.delete(file)
        return True
    
    return commit_or_raise(db, _work)


def _get_file(db: Session, file_id: UUID) -> ProjectFile:
    """
    Obtiene un archivo por ID.
    
    Args:
        db: Sesión SQLAlchemy
        file_id: ID del archivo
        
    Returns:
        Instancia de ProjectFile
        
    Raises:
        FileNotFound: Si el archivo no existe
    """
    file = db.query(ProjectFile).filter(ProjectFile.id == file_id).first()
    if not file:
        raise FileNotFound(file_id)
    return file


__all__ = [
    "add_file",
    "mark_validated",
    "move_file",
    "delete_file",
]
# Fin del archivo backend\app\modules\projects\facades\files\ops.py
