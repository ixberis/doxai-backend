
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/schemas/project_schemas.py

Schemas Pydantic para creación, actualización y respuesta de proyectos.
Alineados con ProjectState/ProjectStatus y ProjectFacade.

BD 2.0 SSOT:
- auth_user_id: UUID canónico de ownership (reemplaza user_id legacy)

Autor: Ixchel Beristáin
Fecha: 28/10/2025
Actualizado: 2026-01-16 - project_slug opcional (auto-generado si no se proporciona)
"""

import re
import unicodedata
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import Field, field_validator, model_validator, ConfigDict

from app.shared.utils.base_models import UTF8SafeModel
from app.modules.projects.enums.project_state_enum import ProjectState
from app.modules.projects.enums.project_status_enum import ProjectStatus


def _generate_slug(name: str) -> str:
    """
    Genera un slug válido a partir de un nombre.
    - Normaliza unicode (remueve acentos)
    - Convierte a lowercase
    - Reemplaza espacios y caracteres no alfanuméricos por guiones
    - Remueve guiones múltiples y al inicio/final
    """
    # Normalizar unicode (remover acentos)
    normalized = unicodedata.normalize('NFKD', name)
    ascii_text = normalized.encode('ascii', 'ignore').decode('ascii')
    # Lowercase y reemplazar no-alfanuméricos por guiones
    slug = re.sub(r'[^a-z0-9]+', '-', ascii_text.lower())
    # Remover guiones al inicio/final y múltiples consecutivos
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug or 'proyecto'


# ========== REQUEST SCHEMAS ==========

class ProjectCreateIn(UTF8SafeModel):
    """
    Request para crear un nuevo proyecto.
    
    Requiere nombre. El slug es opcional y se auto-genera del nombre si no se proporciona.
    """
    project_name: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Nombre del proyecto"
    )
    project_slug: Optional[str] = Field(
        None,
        min_length=3,
        max_length=255,
        description="Slug único del proyecto (opcional, se genera automáticamente)"
    )
    project_description: Optional[str] = Field(
        None,
        max_length=1000,
        description="Descripción opcional del proyecto"
    )

    @field_validator("project_name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        """Valida que el nombre no esté vacío"""
        if not v.strip():
            raise ValueError("El nombre del proyecto no puede estar vacío")
        return v.strip()

    @field_validator("project_slug")
    @classmethod
    def slug_must_be_valid(cls, v: Optional[str]) -> Optional[str]:
        """Valida que el slug sea válido si se proporciona"""
        if v is None:
            return None
        v = v.strip().lower()
        if not v:
            return None
        if " " in v:
            raise ValueError("El slug no puede contener espacios")
        return v

    @field_validator("project_description")
    @classmethod
    def description_strip(cls, v: Optional[str]) -> Optional[str]:
        """Limpia la descripción"""
        return v.strip() if v else None

    @model_validator(mode='after')
    def ensure_slug(self) -> 'ProjectCreateIn':
        """Auto-genera slug si no se proporcionó"""
        if not self.project_slug:
            self.project_slug = _generate_slug(self.project_name)
        return self

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_name": "Análisis de Propuesta Técnica Q4 2025",
                "project_description": "Evaluación de propuesta para licitación gubernamental"
            }
        }
    )


class ProjectUpdateIn(UTF8SafeModel):
    """Request para actualizar campos permitidos del proyecto"""
    project_name: Optional[str] = Field(
        None,
        min_length=3,
        max_length=255,
        description="Nuevo nombre del proyecto"
    )
    project_description: Optional[str] = Field(
        None,
        max_length=1000,
        description="Nueva descripción del proyecto"
    )

    @field_validator("project_name")
    @classmethod
    def name_must_not_be_blank(cls, v: Optional[str]) -> Optional[str]:
        """Valida que el nombre no esté vacío si se proporciona"""
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("El nombre del proyecto no puede estar vacío")
        return v

    @field_validator("project_description")
    @classmethod
    def description_strip(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else None


# ========== RESPONSE SCHEMAS ==========

class ProjectRead(UTF8SafeModel):
    """
    Response completo de un proyecto.
    
    SSOT Contract:
    - Todos los campos se serializan con nombres canónicos de DB
    - project_state: Estado operacional (created, uploading, processing, ready, error, archived)
    - status: Estado de negocio (in_process, closed, retention_grace, deleted_by_policy)
    - Los timestamps de retención siempre se incluyen (pueden ser null)
    
    BD 2.0 SSOT: auth_user_id es el ownership canónico (UUID).
    """
    project_id: UUID = Field(..., alias="id", description="ID único del proyecto")
    auth_user_id: UUID = Field(..., description="ID del usuario propietario (UUID SSOT)")
    project_name: str = Field(..., description="Nombre del proyecto")
    project_slug: str = Field(..., description="Slug único del proyecto")
    project_description: Optional[str] = Field(None, description="Descripción")
    
    # SSOT: Serializamos con nombre canónico "project_state" (alias desde atributo ORM "state")
    project_state: ProjectState = Field(
        ..., 
        alias="state", 
        serialization_alias="project_state",
        description="Estado operacional del proyecto"
    )
    # SSOT: Serializamos con nombre "project_status" para consistencia con frontend
    project_status: ProjectStatus = Field(
        ..., 
        alias="status", 
        serialization_alias="project_status",
        description="Estado de negocio del proyecto"
    )
    
    # Timestamps operativos
    created_at: datetime = Field(..., description="Fecha de creación")
    updated_at: datetime = Field(..., description="Última actualización")
    ready_at: Optional[datetime] = Field(None, description="Fecha cuando alcanzó estado 'ready'")
    archived_at: Optional[datetime] = Field(None, description="Fecha de archivo")
    
    # RFC-FILES-RETENTION-001: Timestamps de retención (SSOT canónico, siempre incluidos)
    closed_at: Optional[datetime] = Field(None, description="Fecha de cierre (anchor de retención)")
    retention_grace_at: Optional[datetime] = Field(None, description="Fecha de gracia de retención")
    deleted_by_policy_at: Optional[datetime] = Field(None, description="Fecha de borrado por política")
    
    # Campos de actividad calculados (opcional, set por queries de listado)
    last_activity_at: Optional[datetime] = Field(
        None,
        description="Máximo entre updated_at y último evento de archivo. Para display de 'Actualizado:'."
    )

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        # Usar alias de serialización para output JSON consistente (project_state, project_status)
        by_alias=True,
        json_schema_extra={
            "example": {
                "project_id": "123e4567-e89b-12d3-a456-426614174000",
                "auth_user_id": "987fcdeb-51a2-43d7-b8f9-123456789abc",
                "project_name": "Propuesta Técnica Q4",
                "project_slug": "propuesta-tecnica-q4",
                "project_description": "Análisis de propuesta",
                "project_state": "ready",
                "project_status": "in_process",
                "created_at": "2025-10-01T10:00:00Z",
                "updated_at": "2025-10-18T15:30:00Z",
                "ready_at": "2025-10-18T15:30:00Z",
                "archived_at": None,
                "closed_at": None,
                "retention_grace_at": None,
                "deleted_by_policy_at": None,
                "last_activity_at": "2025-10-18T16:00:00Z"
            }
        }
    )


class ProjectResponse(UTF8SafeModel):
    """Response wrapper para operaciones de un solo proyecto"""
    success: bool = Field(True, description="Indica si la operación fue exitosa")
    message: str = Field(..., description="Mensaje descriptivo")
    project: ProjectRead = Field(..., description="Datos del proyecto")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Proyecto creado exitosamente",
                "project": {
                    "project_id": "123e4567-e89b-12d3-a456-426614174000",
                    "auth_user_id": "987fcdeb-51a2-43d7-b8f9-123456789abc",
                    "project_name": "Mi Proyecto",
                    "project_slug": "mi-proyecto",
                    "project_description": "Descripción del proyecto",
                    "project_state": "created",
                    "project_status": "in_process",
                    "created_at": "2025-10-25T10:00:00Z",
                    "updated_at": "2025-10-25T10:00:00Z",
                    "ready_at": None,
                    "archived_at": None
                }
            }
        }
    )


class ProjectListResponse(UTF8SafeModel):
    """Response para listados de proyectos"""
    success: bool = Field(True, description="Indica si la operación fue exitosa")
    items: List[ProjectRead] = Field(..., description="Lista de proyectos")
    total: int = Field(..., description="Total de proyectos en la lista")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "items": [],
                "total": 0
            }
        }
    )
# Fin del archivo backend/app/modules/projects/schemas/project_schemas.py
