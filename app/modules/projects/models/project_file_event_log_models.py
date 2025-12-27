
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/models/project_file_event_log_models.py

Modelo SQLAlchemy para auditoría de eventos sobre archivos de proyecto.
Registra el historial de eventos (upload, validate, move, delete) para
auditar actividad y disparar actualizaciones del tablero cliente.

Autor: Ixchel Beristáin
Fecha: 2025-10-24
"""

from uuid import uuid4
from sqlalchemy import Column, String, Text, Numeric, DateTime, ForeignKey, Index, Integer
from sqlalchemy.dialects.postgresql import UUID, CITEXT
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
    de proyecto, con snapshot de metadatos para trazabilidad histórica.
    """

    __tablename__ = "project_file_event_logs"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_file_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_files.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Snapshot del UUID del archivo (preserva información histórica sin FK)
    project_file_id_snapshot = Column(UUID(as_uuid=True), nullable=True)

    # User who performed the action (nullable to support system-triggered events)
    # user_id es int (FK a app_users.user_id que es INTEGER/BIGINT)
    user_id = Column(
        Integer,
        ForeignKey("app_users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    user_email = Column(CITEXT, nullable=True)

    # Event Details
    event_type = Column(
        project_file_event_pg_enum(),
        nullable=False,
        index=True,
    )
    event_details = Column(Text, nullable=True)

    # File Metadata Snapshot (denormalized for historical traceability)
    project_file_name_snapshot = Column(CITEXT, nullable=False)
    project_file_path_snapshot = Column(Text, nullable=False)
    project_file_size_kb_snapshot = Column(Numeric(12, 2), nullable=True)
    project_file_checksum_snapshot = Column(String(128), nullable=True)

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
            "project_file_id",
            "event_type",
        ),
        Index(
            "idx_project_file_event_logs_file_created",
            "project_file_id",
            "created_at",
        ),
    )

    def __repr__(self):
        return (
            f"<ProjectFileEventLog(id={self.id}, "
            f"project_file_id={self.project_file_id}, "
            f"event='{self.event_type}', "
            f"created_at={self.created_at})>"
        )


__all__ = ["ProjectFileEventLog"]
# Fin del archivo backend\app\modules\projects\models\project_file_event_log_models.py