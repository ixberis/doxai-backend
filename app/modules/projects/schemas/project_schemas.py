
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/schemas/project_schemas.py

Schemas Pydantic para creación, actualización y respuesta de proyectos.
Alineados con ProjectState/ProjectStatus y ProjectFacade.

Autor: Ixchel Beristáin
Fecha: 28/10/2025
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import Field, EmailStr, field_validator, ConfigDict

from app.shared.utils.base_models import UTF8SafeModel
from app.modules.projects.enums.project_state_enum import ProjectState
from app.modules.projects.enums.project_status_enum import ProjectStatus


# ========== REQUEST SCHEMAS ==========

class ProjectCreateIn(UTF8SafeModel):
    """
    Request para crear un nuevo proyecto.
    
    Requiere nombre, slug y descripción opcional.
    El slug debe ser único globalmente.
    """
    project_name: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Nombre del proyecto"
    )
    project_slug: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Slug único del proyecto (lowercase, sin espacios)"
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
    def slug_must_be_valid(cls, v: str) -> str:
        """Valida que el slug sea válido (lowercase, sin espacios)"""
        v = v.strip().lower()
        if not v:
            raise ValueError("El slug del proyecto no puede estar vacío")
        if " " in v:
            raise ValueError("El slug no puede contener espacios")
        return v

    @field_validator("project_description")
    @classmethod
    def description_strip(cls, v: Optional[str]) -> Optional[str]:
        """Limpia la descripción"""
        return v.strip() if v else None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_name": "Análisis de Propuesta Técnica Q4 2025",
                "project_slug": "analisis-propuesta-tecnica-q4-2025",
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
    
    Incluye todos los campos del modelo Project alineados con
    ProjectState/ProjectStatus.
    
    Nota: user_id es UUID (consistente con auth.users.id y DDL de producción).
    """
    project_id: UUID = Field(..., alias="id", description="ID único del proyecto")
    user_id: UUID = Field(..., description="ID del usuario propietario (UUID)")
    user_email: EmailStr = Field(..., description="Email del propietario")
    project_name: str = Field(..., description="Nombre del proyecto")
    project_slug: str = Field(..., description="Slug único del proyecto")
    project_description: Optional[str] = Field(None, description="Descripción")
    state: ProjectState = Field(..., description="Estado operacional del proyecto")
    status: ProjectStatus = Field(..., description="Estado de negocio del proyecto")
    created_at: datetime = Field(..., description="Fecha de creación")
    updated_at: datetime = Field(..., description="Última actualización")
    ready_at: Optional[datetime] = Field(None, description="Fecha cuando alcanzó estado 'ready'")
    archived_at: Optional[datetime] = Field(None, description="Fecha de archivo")

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "project_id": "123e4567-e89b-12d3-a456-426614174000",
                "user_id": "987fcdeb-51a2-43d7-b8f9-123456789abc",
                "user_email": "user@example.com",
                "project_name": "Propuesta Técnica Q4",
                "project_slug": "propuesta-tecnica-q4",
                "project_description": "Análisis de propuesta",
                "state": "ready",
                "status": "in_process",
                "created_at": "2025-10-01T10:00:00Z",
                "updated_at": "2025-10-18T15:30:00Z",
                "ready_at": "2025-10-18T15:30:00Z",
                "archived_at": None
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
                    "user_id": "987fcdeb-51a2-43d7-b8f9-123456789abc",
                    "user_email": "user@example.com",
                    "project_name": "Mi Proyecto",
                    "project_slug": "mi-proyecto",
                    "project_description": "Descripción del proyecto",
                    "state": "created",
                    "status": "in_process",
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
