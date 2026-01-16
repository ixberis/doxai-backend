
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/audit_logger.py

Logger unificado para auditoría de proyectos y archivos.
Encapsula formateo de eventos y creación de logs.

IMPORTANTE: Este logger es ASYNC-ONLY y requiere AsyncSession.
Solo hace db.add(), NO hace commit/flush - eso lo maneja commit_or_raise.

Autor: Ixchel Beristain
Fecha: 2025-10-26
Actualizado: 2026-01-16 (async-only, SYSTEM_ACTOR_UUID, no PII)
"""

import os
import logging
from uuid import UUID
from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models.project_action_log_models import ProjectActionLog
from app.modules.projects.models.project_file_event_log_models import ProjectFileEventLog
from app.modules.projects.models.project_file_models import ProjectFile
from app.modules.projects.enums.project_action_type_enum import ProjectActionType
from app.modules.projects.enums.project_file_event_enum import ProjectFileEvent


logger = logging.getLogger(__name__)

# UUID constante para eventos de sistema (auth_user_id NOT NULL en BD 2.0)
# Evita generar uuid4() dinámicos que crean actores "fantasma"
SYSTEM_ACTOR_UUID = UUID("00000000-0000-0000-0000-000000000000")

# Feature flag para ProjectFileEventLog (legacy table con user_id Integer)
# Default OFF en prod para evitar 500s por constraints NOT NULL
PROJECT_FILE_EVENT_LOG_ENABLED = os.getenv("PROJECT_FILE_EVENT_LOG_ENABLED", "false").lower() == "true"


class AuditLogger:
    """
    Logger unificado para auditoría de proyectos y archivos.
    
    Centraliza lógica de formateo y persistencia de logs para:
    - ProjectActionLog (acciones sobre proyectos)
    - ProjectFileEventLog (eventos sobre archivos)
    
    IMPORTANTE: 
    - Este logger es ASYNC-ONLY y requiere AsyncSession
    - Solo hace db.add(), NO hace commit/flush
    - El commit lo maneja commit_or_raise en la transacción envolvente
    """
    
    def __init__(self, db: AsyncSession):
        """
        Args:
            db: AsyncSession SQLAlchemy activa
        """
        self.db = db
    
    def log_action(
        self,
        *,
        project_id: UUID,
        action: ProjectActionType,
        metadata: dict,
        auth_user_id: Optional[UUID] = None,
        **legacy_kwargs: Any,  # Compat: ignora user_id, user_email si llegan
    ) -> ProjectActionLog:
        """
        Registra una acción sobre un proyecto.
        
        SSOT BD 2.0: Usa auth_user_id (UUID) como actor canónico.
        No almacena PII (email, nombre).
        
        Para eventos de sistema (sin usuario), usa SYSTEM_ACTOR_UUID constante
        en lugar de generar uuid4() dinámicos.
        
        Args:
            project_id: ID del proyecto afectado
            action: Tipo de acción (created, updated, deleted)
            metadata: Datos adicionales en formato JSONB
            auth_user_id: UUID del usuario (JWT.sub) - SSOT. None para sistema.
            **legacy_kwargs: Ignorados (compat temporal para user_id, user_email)
            
        Returns:
            Registro de log creado (pendiente de commit por commit_or_raise)
        """
        # Compat temporal: log si llegan kwargs legacy (para detectar callsites viejos)
        if legacy_kwargs:
            ignored = list(legacy_kwargs.keys())
            logger.debug(f"log_action: ignorando kwargs legacy: {ignored}")
        
        effective_auth_user_id = auth_user_id
        
        if effective_auth_user_id is None:
            # Evento de sistema: usar UUID constante, no uuid4()
            metadata = {**metadata, "actor": "system"}
            effective_auth_user_id = SYSTEM_ACTOR_UUID
        
        log_entry = ProjectActionLog(
            project_id=project_id,
            auth_user_id=effective_auth_user_id,
            action_type=action,
            action_metadata=metadata
        )
        
        # Solo add, NO flush/commit - eso lo hace commit_or_raise
        self.db.add(log_entry)
        return log_entry
    
    def log_file_event(
        self,
        *,
        project_id: UUID,
        file_id: UUID,
        auth_user_id: Optional[UUID],
        event: ProjectFileEvent,
        file_snapshot: ProjectFile,
        old_path: Optional[str] = None
    ) -> Optional[ProjectFileEventLog]:
        """
        Registra un evento sobre un archivo de proyecto.
        
        FEATURE FLAG: Controlado por PROJECT_FILE_EVENT_LOG_ENABLED.
        Si está OFF (default en prod), retorna None sin insertar para
        evitar 500s por constraints NOT NULL en tabla legacy.
        
        Guarda snapshots de metadatos del archivo para auditoría.
        
        NOTA: ProjectFileEventLog aún usa user_id (Integer) por compatibilidad
        con la tabla existente. Este método acepta auth_user_id pero el modelo
        requiere migración separada.
        
        Args:
            project_id: ID del proyecto
            file_id: ID del archivo
            auth_user_id: UUID del usuario (None para sistema)
            event: Tipo de evento (uploaded, validated, moved, deleted)
            file_snapshot: Instancia del archivo para obtener metadatos
            old_path: Ruta anterior (requerido para eventos 'moved')
            
        Returns:
            Registro de evento creado, o None si feature flag está OFF
            
        Raises:
            AssertionError: Si old_path no se provee para evento 'moved'
        """
        # Feature flag: skip insert si deshabilitado (default en prod)
        if not PROJECT_FILE_EVENT_LOG_ENABLED:
            logger.debug(
                f"log_file_event: skipped (PROJECT_FILE_EVENT_LOG_ENABLED=false) "
                f"project={project_id}, file={file_id}, event={event.value}"
            )
            return None
        
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
        
        # NOTA: ProjectFileEventLog usa user_id (Integer) y user_email (legacy)
        # Esto requiere migración de BD separada. Por ahora, pasamos None.
        log_entry = ProjectFileEventLog(
            project_id=project_id,
            project_file_id=file_id,
            project_file_id_snapshot=file_id,
            user_id=None,  # Legacy Integer FK - requires separate migration
            user_email=None,  # Legacy - no PII
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


__all__ = ["AuditLogger", "SYSTEM_ACTOR_UUID", "PROJECT_FILE_EVENT_LOG_ENABLED"]
# Fin del archivo backend/app/modules/projects/facades/audit_logger.py
