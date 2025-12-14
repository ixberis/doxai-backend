
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/audit_logger.py

Logger unificado para auditoría de proyectos y archivos.
Encapsula formateo de eventos y creación de logs.

Autor: Ixchel Beristain
Fecha: 2025-10-26
"""

from uuid import UUID
from typing import Optional
from sqlalchemy.orm import Session

from app.modules.projects.models.project_action_log_models import ProjectActionLog
from app.modules.projects.models.project_file_event_log_models import ProjectFileEventLog
from app.modules.projects.models.project_file_models import ProjectFile
from app.modules.projects.enums.project_action_type_enum import ProjectActionType
from app.modules.projects.enums.project_file_event_enum import ProjectFileEvent


class AuditLogger:
    """
    Logger unificado para auditoría de proyectos y archivos.
    
    Centraliza lógica de formateo y persistencia de logs para:
    - ProjectActionLog (acciones sobre proyectos)
    - ProjectFileEventLog (eventos sobre archivos)
    """
    
    def __init__(self, db: Session):
        """
        Args:
            db: Sesión SQLAlchemy activa
        """
        self.db = db
    
    def log_action(
        self,
        project_id: UUID,
        user_id: Optional[UUID],
        user_email: Optional[str],
        action: ProjectActionType,
        metadata: dict
    ) -> ProjectActionLog:
        """
        Registra una acción sobre un proyecto.
        
        Soporta eventos de sistema (user_id=None, user_email=None).
        
        Args:
            project_id: ID del proyecto afectado
            user_id: ID del usuario que ejecuta la acción (None para sistema)
            user_email: Email del usuario (None para sistema)
            action: Tipo de acción (created, updated, deleted)
            metadata: Datos adicionales en formato JSONB
            
        Returns:
            Registro de log creado
        """
        # Si no hay usuario, es un evento de sistema
        if user_id is None:
            metadata = {**metadata, "actor": "system"}
        
        log_entry = ProjectActionLog(
            project_id=project_id,
            user_id=user_id,
            user_email=user_email,
            action_type=action,
            action_metadata=metadata
        )
        
        self.db.add(log_entry)
        return log_entry
    
    def log_file_event(
        self,
        project_id: UUID,
        file_id: UUID,
        user_id: UUID,
        user_email: str,
        event: ProjectFileEvent,
        file_snapshot: ProjectFile,
        old_path: Optional[str] = None
    ) -> ProjectFileEventLog:
        """
        Registra un evento sobre un archivo de proyecto.
        
        Guarda snapshots de metadatos del archivo para auditoría.
        
        Args:
            project_id: ID del proyecto
            file_id: ID del archivo
            user_id: ID del usuario que ejecuta el evento
            user_email: Email del usuario
            event: Tipo de evento (uploaded, validated, moved, deleted)
            file_snapshot: Instancia del archivo para obtener metadatos
            old_path: Ruta anterior (requerido para eventos 'moved')
            
        Returns:
            Registro de evento creado
            
        Raises:
            AssertionError: Si old_path no se provee para evento 'moved'
        """
        # Validar old_path para eventos 'moved'
        if event == ProjectFileEvent.moved:
            assert old_path is not None, "old_path requerido para evento 'moved'"
        
        # Calcular tamaño en KB para snapshot
        size_kb = None
        if file_snapshot.size_bytes is not None:
            size_kb = file_snapshot.size_bytes / 1024.0
        
        # Preparar detalles del evento según tipo
        event_details = self._format_event_details(
            event=event,
            file_snapshot=file_snapshot,
            size_kb=size_kb,
            old_path=old_path
        )
        
        log_entry = ProjectFileEventLog(
            project_id=project_id,
            project_file_id=file_id,
            project_file_id_snapshot=file_id,
            user_id=user_id,
            user_email=user_email,
            event_type=event,
            event_details=event_details,
            project_file_name_snapshot=file_snapshot.filename,
            project_file_path_snapshot=file_snapshot.path,
            project_file_size_kb_snapshot=size_kb,
            project_file_checksum_snapshot=file_snapshot.checksum
        )
        
        self.db.add(log_entry)
        return log_entry
    
    def _format_event_details(
        self,
        event: ProjectFileEvent,
        file_snapshot: ProjectFile,
        size_kb: Optional[float],
        old_path: Optional[str]
    ) -> str:
        """
        Formatea los detalles de un evento de archivo.
        
        Genera mensajes legibles para auditoría según el tipo de evento.
        
        Args:
            event: Tipo de evento
            file_snapshot: Snapshot del archivo
            size_kb: Tamaño en KB (None si no disponible)
            old_path: Ruta anterior (para eventos 'moved')
            
        Returns:
            String formateado con detalles del evento
        """
        filename = file_snapshot.filename
        mime_type = file_snapshot.mime_type or 'unknown'
        checksum = file_snapshot.checksum or 'n/a'
        
        if event == ProjectFileEvent.uploaded:
            if size_kb:
                return f"Uploaded: {filename} ({mime_type}, {size_kb:.2f} KB)"
            return f"Uploaded: {filename} ({mime_type})"
        
        elif event == ProjectFileEvent.validated:
            if size_kb:
                return f"Validated: {filename} ({mime_type}, {size_kb:.2f} KB)"
            return f"Validated: {filename}"
        
        elif event == ProjectFileEvent.moved:
            return f"Moved from {old_path} to {file_snapshot.path}"
        
        elif event == ProjectFileEvent.deleted:
            if size_kb:
                return f"Deleted: {filename} ({mime_type}, {size_kb:.2f} KB, checksum: {checksum})"
            return f"Deleted: {filename}"
        
        # Fallback genérico
        return f"{event.value}: {filename}"


__all__ = ["AuditLogger"]
# Fin del archivo backend/app/modules/projects/facades/audit_logger.py
