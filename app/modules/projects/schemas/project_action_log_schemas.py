
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/schemas/project_action_log_schemas.py

Schemas Pydantic para auditoría de acciones de proyectos.
Alineados con ProjectActionLog y ProjectActionType.

Autor: DoxAI
Fecha: 2025-10-25
"""

from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from pydantic import Field, EmailStr, ConfigDict

from app.shared.utils.base_models import UTF8SafeModel
from app.modules.projects.enums.project_action_type_enum import ProjectActionType


# ========== INPUT SCHEMAS ==========

class ProjectActionLogCreateIn(UTF8SafeModel):
    """
    Schema para crear un nuevo log de acción del proyecto.
    """
    project_id: UUID = Field(..., description="ID del proyecto")
    user_id: Optional[UUID] = Field(None, description="ID del usuario que realiza la acción (None para sistema)")
    user_email: Optional[EmailStr] = Field(None, description="Email del usuario (None para sistema)")
    action_type: ProjectActionType = Field(..., description="Tipo de acción")
    action_details: Optional[str] = Field(None, description="Detalle textual de la acción")
    action_metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata JSON adicional")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "123e4567-e89b-12d3-a456-426614174000",
                "user_id": "987fcdeb-51a2-43d7-b8f9-123456789abc",
                "user_email": "user@example.com",
                "action_type": "updated",
                "action_details": "Proyecto actualizado exitosamente",
                "action_metadata": {"field": "description"}
            }
        }
    )


# Alias legacy para tests antiguos
ProjectActivityCreate = ProjectActionLogCreateIn


# ========== RESPONSE SCHEMAS ==========

class ProjectActionLogRead(UTF8SafeModel):
    """
    Response de un log de acción del proyecto.
    
    Mapea 1:1 con el modelo ProjectActionLog.
    """
    action_log_id: UUID = Field(..., alias="id", description="ID único del log de acción")
    project_id: UUID = Field(..., description="ID del proyecto")
    user_id: Optional[UUID] = Field(None, description="ID del usuario que realizó la acción (None para sistema)")
    user_email: Optional[EmailStr] = Field(None, description="Email del usuario (None para sistema)")
    action_type: ProjectActionType = Field(..., description="Tipo de acción")
    action_details: Optional[str] = Field(None, description="Detalle textual de la acción")
    action_metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata JSON adicional")
    created_at: datetime = Field(..., description="Timestamp de la acción")

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "action_log_id": "456e7890-a12b-34c5-d678-901234567890",
                "project_id": "123e4567-e89b-12d3-a456-426614174000",
                "user_id": "987fcdeb-51a2-43d7-b8f9-123456789abc",
                "user_email": "user@example.com",
                "action_type": "created",
                "action_details": "Proyecto creado",
                "action_metadata": {
                    "project_name": "Mi Proyecto",
                    "project_slug": "mi-proyecto"
                },
                "created_at": "2025-10-18T10:00:00Z"
            }
        }
    )


# ========== QUERY SCHEMAS ==========

class ProjectActionLogQuery(UTF8SafeModel):
    """
    Filtros para consulta de logs de acciones.
    
    Alineado con ProjectQueryFacade.list_actions().
    """
    project_id: UUID = Field(..., description="ID del proyecto")
    action_type: Optional[ProjectActionType] = Field(
        None,
        description="Filtrar por tipo de acción específico"
    )
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

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "123e4567-e89b-12d3-a456-426614174000",
                "action_type": "updated",
                "limit": 50,
                "offset": 0
            }
        }
    )


class ProjectActionLogListResponse(UTF8SafeModel):
    """Response para listado de logs de acciones"""
    success: bool = Field(True, description="Indica si la operación fue exitosa")
    items: List[ProjectActionLogRead] = Field(..., description="Lista de logs de acciones")
    total: int = Field(..., description="Total de logs en la lista")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "items": [],
                "total": 0
            }
        }
    )
# Fin del archivo backend/app/modules/projects/schemas/project_action_log_schemas.py
