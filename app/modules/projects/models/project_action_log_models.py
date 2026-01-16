
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/models/project_action_log_models.py

Logs de acciones sobre proyectos (auditoría).

Autor: Ixchel Beristáin
Fecha: 28/10/2025
"""

from uuid import uuid4
from sqlalchemy import Column, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, CITEXT
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.shared.database import Base
from app.modules.projects.enums.project_action_type_enum import (
    ProjectActionType,
    as_pg_enum as project_action_type_pg_enum,
)


class ProjectActionLog(Base):
    __tablename__ = "project_action_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Actor canónico por auth_user_id (UUID) - SSOT BD 2.0
    # No almacenar PII (email, nombre) aquí
    auth_user_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Acción realizada
    action_type = Column(
        project_action_type_pg_enum(),
        nullable=False,
        index=True,
    )
    action_details = Column(CITEXT, nullable=True)

    # Metadata adicional (JSON)
    action_metadata = Column(JSONB, nullable=False, server_default="{}")

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    project = relationship("Project", backref="action_logs")

    __table_args__ = (
        # Usa ATRIBUTOS, no strings, para evitar desfaces de nombres reales
        Index("idx_proj_action_logs_proj_created_at", project_id, created_at),
        Index("idx_proj_action_logs_type_created_at", action_type, created_at),
        Index("idx_proj_action_logs_auth_user_created_at", auth_user_id, created_at),
    )

    def __repr__(self):
        return (
            f"<ProjectActionLog(id={self.id}, "
            f"project_id={self.project_id}, "
            f"action_type={self.action_type})>"
        )


__all__ = ["ProjectActionLog"]
# Fin del archivo backend/app/modules/projects/models/project_action_log_models.py