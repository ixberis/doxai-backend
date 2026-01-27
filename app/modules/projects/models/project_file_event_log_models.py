
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/models/project_file_event_log_models.py

Modelo SQLAlchemy para auditoría de eventos sobre archivos de proyecto.
Registra el historial de eventos (upload, validate, move, delete) para
auditar actividad y disparar actualizaciones del tablero cliente.

BD 2.0 SSOT:
- file_id referencia files_base(file_id), NO project_files (eliminado).
- FK se crea condicionalmente en 04_foreign_keys_projects.sql si files_base existe.

Autor: Ixchel Beristáin
Fecha: 2025-10-24
Actualizado: 2026-01-27 - Eliminar FK a project_files legacy (BD 2.0 SSOT)
"""

from uuid import uuid4
from sqlalchemy import Column, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from app.shared.database import Base
from app.modules.projects.enums.project_file_event_enum import (
    ProjectFileEvent,
    as_pg_enum as project_file_event_pg_enum,
)


class ProjectFileEventLog(Base):
    """
    Modelo de auditoría de eventos sobre archivos de proyecto.

    Registra eventos como uploaded, validated, moved, deleted sobre archivos
    de proyecto. BD 2.0 SSOT: file_id referencia files_base, no project_files.
    
    Los metadatos del evento se almacenan en event_metadata (JSONB) para
    flexibilidad y compatibilidad con el esquema SQL canónico.
    """

    __tablename__ = "project_file_event_logs"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Relación al proyecto (CASCADE en DB)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # BD 2.0 SSOT: file_id referencia files_base (Files 2.0)
    # La FK se crea en SQL canónico si files_base existe
    # NO hay FK ORM aquí para evitar errores de mappers
    file_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Event Details
    event_type = Column(
        project_file_event_pg_enum(),
        nullable=False,
        index=True,
    )
    
    # BD 2.0 SSOT: event_metadata (JSONB) en lugar de columnas snapshot legacy
    event_metadata = Column(
        JSONB,
        nullable=False,
        server_default="{}",
    )

    # Timestamp
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    # Composite indexes for common queries
    __table_args__ = (
        Index(
            "idx_project_file_event_logs_project_created",
            "project_id",
            "created_at",
        ),
        Index(
            "idx_project_file_event_logs_file_event",
            "file_id",
            "event_type",
        ),
    )

    def __repr__(self):
        return (
            f"<ProjectFileEventLog(id={self.id}, "
            f"file_id={self.file_id}, "
            f"event='{self.event_type}', "
            f"created_at={self.created_at})>"
        )


__all__ = ["ProjectFileEventLog"]
# Fin del archivo backend/app/modules/projects/models/project_file_event_log_models.py