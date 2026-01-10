
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/schemas/project_query_schemas.py

Schemas Pydantic para consultas y filtros de proyectos.
Alineados con ProjectQueryFacade.

BD 2.0 SSOT:
- auth_user_id: UUID canónico de ownership (reemplaza user_id legacy)

Autor: DoxAI
Fecha: 2025-10-25
Actualizado: 2026-01-10 - BD 2.0 SSOT: user_id → auth_user_id
"""

from typing import Optional
from uuid import UUID
from pydantic import Field, ConfigDict

from app.shared.utils.base_models import UTF8SafeModel
from app.modules.projects.enums.project_state_enum import ProjectState
from app.modules.projects.enums.project_status_enum import ProjectStatus


# ========== QUERY SCHEMAS ==========

class ProjectListByUserQuery(UTF8SafeModel):
    """
    Filtros para listar proyectos de un usuario.
    
    Alineado con ProjectQueryFacade.list_by_user().
    BD 2.0 SSOT: auth_user_id es el ownership canónico.
    """
    auth_user_id: UUID = Field(..., description="ID del usuario (UUID SSOT)")
    state: Optional[ProjectState] = Field(
        None,
        description="Filtrar por estado operacional específico"
    )
    status: Optional[ProjectStatus] = Field(
        None,
        description="Filtrar por estado de negocio específico"
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Número máximo de resultados (máx. 200)"
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Número de resultados a saltar para paginación"
    )
    include_total: bool = Field(
        default=False,
        description="Si True, retorna tupla (items, total); si False, solo items"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "auth_user_id": "987fcdeb-51a2-43d7-b8f9-123456789abc",
                "state": "ready",
                "status": "in_process",
                "limit": 50,
                "offset": 0,
                "include_total": True
            }
        }
    )


class ProjectListReadyQuery(UTF8SafeModel):
    """
    Filtros para listar proyectos en estado 'ready'.
    
    Alineado con ProjectQueryFacade.list_ready_projects().
    BD 2.0 SSOT: auth_user_id es el ownership canónico.
    """
    auth_user_id: Optional[UUID] = Field(
        None,
        description="Filtrar por usuario específico (opcional, UUID SSOT)"
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Número máximo de resultados (máx. 200)"
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Número de resultados a saltar para paginación"
    )
    include_total: bool = Field(
        default=False,
        description="Si True, retorna tupla (items, total); si False, solo items"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "auth_user_id": "987fcdeb-51a2-43d7-b8f9-123456789abc",
                "limit": 50,
                "offset": 0,
                "include_total": True
            }
        }
    )


class ProjectListFilesQuery(UTF8SafeModel):
    """
    Filtros para listar archivos de un proyecto.
    
    Alineado con ProjectQueryFacade.list_files().
    """
    project_id: UUID = Field(..., description="ID del proyecto")
    limit: int = Field(
        default=100,
        ge=1,
        le=200,
        description="Número máximo de resultados (máx. 200)"
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Número de resultados a saltar para paginación"
    )
    include_total: bool = Field(
        default=False,
        description="Si True, retorna tupla (items, total); si False, solo items"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "123e4567-e89b-12d3-a456-426614174000",
                "limit": 100,
                "offset": 0,
                "include_total": True
            }
        }
    )
# Fin del archivo backend/app/modules/projects/schemas/project_query_schemas.py
