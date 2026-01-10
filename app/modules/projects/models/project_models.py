
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/models/project_models.py

Modelo SQLAlchemy para proyectos de usuario en DoxAI.
Usa ProjectState (ciclo operativo) y ProjectStatus (situación de negocio).

BD 2.0 SSOT:
- auth_user_id (UUID): Columna canónica de ownership (NOT NULL)
- user_email: Mantener para compatibilidad/búsquedas (CITEXT)

Autor: Ixchel Beristáin
Fecha: 2025-10-24
Actualizado: 2026-01-10 - BD 2.0 SSOT: user_id → auth_user_id
"""

from uuid import uuid4
from sqlalchemy import Column, String, Text, DateTime, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.shared.database import Base
from app.modules.projects.enums.project_state_enum import (
    ProjectState,
    as_pg_enum as project_state_pg_enum,
)
from app.modules.projects.enums.project_status_enum import (
    ProjectStatus,
    as_pg_enum as project_status_pg_enum,
)


class Project(Base):
    """
    Modelo de proyecto de usuario.

    Distinción semántica:
    - state (ProjectState): Ciclo de vida técnico
      (created→uploading→processing→ready/error→archived)
    - status (ProjectStatus): Situación de negocio/administrativa
      (in_process, etc.)

    BD 2.0 SSOT:
    - auth_user_id: UUID del usuario propietario (SSOT canónico)

    Timestamps especiales:
    - ready_at: se setea cuando state transiciona a 'ready'
    - archived_at: se setea cuando state transiciona a 'archived'
    """

    __tablename__ = "projects"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # BD 2.0 SSOT: auth_user_id es el ownership canónico (UUID)
    # NO hay columna user_email en la tabla projects de BD 2.0.
    # Si se necesita el email, se hace JOIN con app_users via auth_user_id.
    auth_user_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Nota: Audit trail (created_by/updated_by) se maneja en tablas de log,
    # no en la tabla projects (diseño por eventos/logs).

    # Project Identity
    project_name = Column(String(255), nullable=False)
    project_slug = Column(String(255), nullable=False, unique=True, index=True)
    project_description = Column(Text, nullable=True)

    # Project State (operational/technical lifecycle)
    state = Column(
        project_state_pg_enum(),
        nullable=False,
        server_default=ProjectState.created.value,
        index=True,
        name="project_state",
    )

    # Project Status (administrative/business situation)
    status = Column(
        project_status_pg_enum(),
        nullable=False,
        server_default=ProjectStatus.in_process.value,
        index=True,
        name="project_status",
    )

    # Timestamps (SIN prefijo en DB - nomenclatura inconsistente)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    ready_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )
    archived_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    files = relationship(
        "ProjectFile",
        back_populates="project",
        cascade="all, delete-orphan",
    )

    # Composite indexes for common queries
    __table_args__ = (
        # BD 2.0: índice compuesto usa auth_user_id
        Index("idx_projects_auth_user_state", auth_user_id, state),
        Index("idx_projects_state_status", state, status),
        # Parcial: prioriza proyectos listos por fecha de listo
        Index(
            "idx_projects_ready_at_ready",
            ready_at,
            postgresql_where=(state == ProjectState.ready),
        ),
    )

    def __repr__(self):
        return (
            f"<Project(id={self.id}, "
            f"name='{self.project_name}', "
            f"state={self.state}, "
            f"status={self.status})>"
        )


__all__ = ["Project"]
# Fin del archivo backend/app/modules/projects/models/project_models.py
