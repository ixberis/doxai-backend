
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/models/project_file_models.py

Modelo SQLAlchemy para archivos de proyecto.
Representa archivos asociados a un proyecto con metadata básica.

Autor: Ixchel Beristáin
Fecha: 2025-10-24
"""

from uuid import uuid4
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, CITEXT
from sqlalchemy.sql import func

from app.shared.database import Base


class ProjectFile(Base):
    """
    Modelo de archivo de proyecto.

    Representa archivos subidos/asociados a un proyecto.
    Los eventos sobre estos archivos se registran en ProjectFileEventLog.
    """

    __tablename__ = "project_files"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Project Relationship
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # File Metadata
    path = Column(Text, nullable=False, name="project_file_path")
    filename = Column(
        CITEXT,
        nullable=False,
        index=True,
        name="project_file_name",
    )
    mime_type = Column(
        String(255),
        nullable=True,
        name="project_file_mime_type",
    )
    size_bytes = Column(
        Integer,
        nullable=True,
        name="project_file_size_bytes",
    )
    checksum = Column(
        String(128),
        nullable=True,
        name="project_file_checksum",
    )

    # User who uploaded the file (unified naming with event logs)
    # user_id es int (FK a app_users.user_id que es INTEGER/BIGINT)
    user_id = Column(
        Integer,
        ForeignKey("app_users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    user_email = Column(CITEXT, nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
        name="project_file_created_at",
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        name="project_file_updated_at",
    )

    # Relationships
    project = relationship("Project", back_populates="files")

    # Composite indexes for common queries
    __table_args__ = (
        Index(
            "idx_project_files_project_created",
            "project_id",
            "project_file_created_at",
        ),
        Index(
            "idx_project_files_project_filename",
            "project_id",
            "project_file_name",
        ),
    )

    def __repr__(self):
        return (
            f"<ProjectFile(id={self.id}, "
            f"filename='{self.filename}', "
            f"project={self.project_id})>"
        )


__all__ = ["ProjectFile"]
# Fin del archivo backend\app\modules\projects\models\project_file_models.py