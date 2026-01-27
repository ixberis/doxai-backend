
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/audit_logger.py

Logger unificado para auditoría de proyectos.
Encapsula formateo de eventos y creación de logs.

BD 2.0 SSOT (2026-01-27):
- Eliminado log_file_event (tabla project_files no existe)
- Files 2.0 es el SSOT de archivos y tiene su propio logging
- Solo mantiene log_action para ProjectActionLog

IMPORTANTE: Este logger es ASYNC-ONLY y requiere AsyncSession.
Solo hace db.add(), NO hace commit/flush - eso lo maneja commit_or_raise.

Autor: Ixchel Beristain
Fecha: 2025-10-26
Actualizado: 2026-01-27 - Eliminar log_file_event legacy
"""

import logging
from uuid import UUID
from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models.project_action_log_models import ProjectActionLog
from app.modules.projects.enums.project_action_type_enum import ProjectActionType


logger = logging.getLogger(__name__)

# UUID constante para eventos de sistema (auth_user_id NOT NULL en BD 2.0)
# Evita generar uuid4() dinámicos que crean actores "fantasma"
SYSTEM_ACTOR_UUID = UUID("00000000-0000-0000-0000-000000000000")


class AuditLogger:
    """
    Logger unificado para auditoría de proyectos.
    
    Centraliza lógica de formateo y persistencia de logs para:
    - ProjectActionLog (acciones sobre proyectos)
    
    BD 2.0 SSOT:
    - NO hay log_file_event (Files 2.0 maneja su propia auditoría)
    
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
        action_type: ProjectActionType,
        action_details: Optional[str] = None,
        action_metadata: Optional[dict] = None,
        auth_user_id: Optional[UUID] = None,
        # Legacy parameter names (mapped to new names)
        action: Optional[ProjectActionType] = None,  # -> action_type
        metadata: Optional[dict] = None,  # -> action_metadata
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
            action_type: Tipo de acción (created, updated, deleted)
            action_details: Descripción textual de la acción (NO PII)
            action_metadata: Datos adicionales en formato JSONB
            auth_user_id: UUID del usuario (JWT.sub) - SSOT. None para sistema.
            action: (Legacy) Alias de action_type
            metadata: (Legacy) Alias de action_metadata
            **legacy_kwargs: Ignorados (compat temporal para user_id, user_email)
            
        Returns:
            Registro de log creado (pendiente de commit por commit_or_raise)
        """
        # Compat temporal: log si llegan kwargs legacy (para detectar callsites viejos)
        if legacy_kwargs:
            ignored = list(legacy_kwargs.keys())
            logger.debug(f"log_action: ignorando kwargs legacy: {ignored}")
        
        # Map legacy parameter names to canonical names
        effective_action_type = action_type or action
        if effective_action_type is None:
            raise ValueError("action_type is required")
        
        effective_metadata = action_metadata if action_metadata is not None else (metadata or {})
        
        effective_auth_user_id = auth_user_id
        
        if effective_auth_user_id is None:
            # Evento de sistema: usar UUID constante, no uuid4()
            effective_metadata = {**effective_metadata, "actor": "system"}
            effective_auth_user_id = SYSTEM_ACTOR_UUID
        
        log_entry = ProjectActionLog(
            project_id=project_id,
            auth_user_id=effective_auth_user_id,
            action_type=effective_action_type,
            action_details=action_details,  # TEXT NULL - for human-readable context
            action_metadata=effective_metadata,
        )
        
        # Solo add, NO flush/commit - eso lo hace commit_or_raise
        self.db.add(log_entry)
        return log_entry


__all__ = ["AuditLogger", "SYSTEM_ACTOR_UUID"]
# Fin del archivo backend/app/modules/projects/facades/audit_logger.py
