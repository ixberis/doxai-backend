
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/schemas/project_file_event_log_schemas.py

Schemas Pydantic para la bitácora de eventos sobre archivos de proyecto.
Alineados con ProjectFileEventLog y ProjectFileEvent.

BD 2.0 SSOT (2026-01-27):
- file_id referencia files_base (Files 2.0), NO project_files
- event_metadata (JSONB) en lugar de columnas snapshot legacy
- Eliminadas columnas: project_file_id, user_id, user_email, snapshots

Autor: DoxAI
Fecha: 2025-11-10
Actualizado: 2026-01-27 - BD 2.0 SSOT
"""

from typing import Optional, List, Any, Dict
from uuid import UUID
from datetime import datetime
import json

from pydantic import Field, field_validator, ConfigDict

from app.shared.utils.base_models import UTF8SafeModel
from app.modules.projects.enums.project_file_event_enum import ProjectFileEvent


# ========== RESPONSE SCHEMAS ==========

class ProjectFileEventLogRead(UTF8SafeModel):
    """
    Response 'completo' de un log de evento de archivo de proyecto.

    BD 2.0 SSOT:
    - file_id referencia files_base (Files 2.0)
    - event_metadata almacena datos adicionales en JSONB
    """
    project_file_event_log_id: UUID = Field(..., alias="id", description="ID único del log de evento")
    project_id: UUID = Field(..., description="ID del proyecto")
    file_id: UUID = Field(..., description="ID del archivo (files_base.file_id)")
    event_type: ProjectFileEvent = Field(..., description="Tipo de evento")
    event_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata del evento en formato JSONB"
    )
    event_created_at: datetime = Field(
        ...,
        alias="created_at",
        description="Timestamp del evento",
    )

    @field_validator("event_metadata", mode="before")
    @classmethod
    def parse_event_metadata(cls, v: Optional[Any]) -> Dict[str, Any]:
        """
        Asegura que event_metadata sea un dict.
        """
        if v is None:
            return {}
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return {"raw": v}
        return {}

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "project_file_event_log_id": "789e0123-b45c-67d8-e901-234567890abc",
                "project_id": "123e4567-e89b-12d3-a456-426614174000",
                "file_id": "456e7890-a12b-34c5-d678-901234567890",
                "event_type": "uploaded",
                "event_metadata": {"filename": "documento.pdf", "size_bytes": 1048576},
                "event_created_at": "2025-10-18T10:00:00Z"
            }
        }
    )


# Variante 'lite' para listados: payload reducido
class ProjectFileEventLogLite(UTF8SafeModel):
    project_file_event_log_id: UUID = Field(..., alias="id")
    project_id: UUID
    file_id: UUID
    event_type: ProjectFileEvent
    event_created_at: datetime = Field(..., alias="created_at")

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "project_file_event_log_id": "789e0123-b45c-67d8-e901-234567890abc",
                "project_id": "123e4567-e89b-12d3-a456-426614174000",
                "file_id": "456e7890-a12b-34c5-d678-901234567890",
                "event_type": "uploaded",
                "event_created_at": "2025-10-18T10:00:00Z"
            }
        }
    )


# ========== QUERY SCHEMAS ==========

class ProjectFileEventLogQuery(UTF8SafeModel):
    """
    Filtros para consulta de logs de eventos de archivos.

    BD 2.0: file_id referencia files_base.
    """
    project_id: UUID = Field(..., description="ID del proyecto")
    file_id: Optional[UUID] = Field(
        None,
        description="Filtrar por ID de archivo específico (files_base.file_id)"
    )
    event_type: Optional[ProjectFileEvent] = Field(
        None,
        description="Filtrar por tipo de evento específico"
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
        description="Número de resultados a saltar para paginación (fallback)"
    )

    # Cursores opcionales para paginación tipo seek-based
    after_created_at: Optional[datetime] = Field(
        default=None,
        description="Cursor: timestamp (ISO8601) del último evento de la página previa"
    )
    after_id: Optional[UUID] = Field(
        default=None,
        description="Cursor: id (UUID) del último evento de la página previa"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "123e4567-e89b-12d3-a456-426614174000",
                "file_id": "456e7890-a12b-34c5-d678-901234567890",
                "event_type": "uploaded",
                "limit": 50,
                "offset": 0,
                "after_created_at": "2025-10-18T10:00:00Z",
                "after_id": "789e0123-b45c-67d8-e901-234567890abc"
            }
        }
    )


# ========== LIST RESPONSES ==========

class ProjectFileEventLogListResponse(UTF8SafeModel):
    """Response para listado 'completo' de logs de eventos de archivos"""
    success: bool = Field(True, description="Indica si la operación fue exitosa")
    items: List[ProjectFileEventLogRead] = Field(..., description="Lista de logs de eventos")
    total: int = Field(..., description="Total de logs en la lista")
    # Metadatos de cursor (opcionales, sólo cuando se usa seek-based)
    next_after_created_at: Optional[datetime] = Field(
        default=None,
        description="Cursor a usar en la siguiente página (timestamp)"
    )
    next_after_id: Optional[UUID] = Field(
        default=None,
        description="Cursor a usar en la siguiente página (id, UUID)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "items": [],
                "total": 0,
                "next_after_created_at": None,
                "next_after_id": None
            }
        }
    )


class ProjectFileEventLogListLiteResponse(UTF8SafeModel):
    """Response para listado 'lite' (payload reducido) de logs de eventos"""
    success: bool = Field(True)
    items: List[ProjectFileEventLogLite]
    total: int
    next_after_created_at: Optional[datetime] = None
    next_after_id: Optional[UUID] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "items": [],
                "total": 0,
                "next_after_created_at": None,
                "next_after_id": None
            }
        }
    )


# Fin del archivo backend/app/modules/projects/schemas/project_file_event_log_schemas.py
