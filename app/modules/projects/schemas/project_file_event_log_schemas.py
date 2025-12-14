
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/schemas/project_file_event_log_schemas.py

Schemas Pydantic para la bitácora de eventos sobre archivos de proyecto.
Alineados con ProjectFileEventLog y ProjectFileEvent.

Ajuste 10/11/2025:
- Cambia created_at -> event_created_at para alinear con el modelo/índices.
- Agrega metadatos de cursor en las respuestas (next_after_created_at, next_after_id).
- Incorpora variantes 'Lite' para listados de alto volumen (payload reducido).
- Validador de event_details acepta dict o string sin reprocesar innecesariamente.

Ajuste 21/11/2025 (Projects v2):
- event_created_at mapea al atributo ORM created_at mediante alias="created_at".
- Cursores after_id / next_after_id ahora son UUID (id del log), no int.

Autor: DoxAI
Fecha: 2025-11-10 / Actualizado 2025-11-21
"""

from typing import Optional, List, Union, Any, Dict
from uuid import UUID
from datetime import datetime
from decimal import Decimal
import json

from pydantic import Field, EmailStr, field_validator, ConfigDict

from app.shared.utils.base_models import UTF8SafeModel
from app.modules.projects.enums.project_file_event_enum import ProjectFileEvent


# ========== RESPONSE SCHEMAS ==========

class ProjectFileEventLogRead(UTF8SafeModel):
    """
    Response 'completo' de un log de evento de archivo de proyecto.

    Mapea 1:1 con el modelo ProjectFileEventLog, incluyendo todos
    los campos snapshot del archivo al momento del evento.
    """
    project_file_event_log_id: UUID = Field(..., alias="id", description="ID único del log de evento")
    project_id: UUID = Field(..., description="ID del proyecto")
    project_file_id: Optional[UUID] = Field(
        None,
        description="ID del archivo (NULL si fue eliminado con ON DELETE SET NULL)"
    )
    project_file_id_snapshot: Optional[UUID] = Field(
        None,
        description="Snapshot del ID del archivo para preservar historia"
    )
    user_id: Optional[UUID] = Field(
        None,
        description="ID del usuario que generó el evento (None para sistema)"
    )
    user_email: Optional[EmailStr] = Field(
        None,
        description="Email del usuario (None para sistema)"
    )
    event_type: ProjectFileEvent = Field(..., description="Tipo de evento")
    event_details: Optional[Union[str, Dict[str, Any]]] = Field(
        None,
        description="Detalles adicionales del evento (JSON o texto)"
    )

    # Snapshots de metadatos del archivo
    project_file_name_snapshot: str = Field(..., description="Nombre del archivo al momento del evento")
    project_file_path_snapshot: str = Field(..., description="Ruta del archivo al momento del evento")
    project_file_size_kb_snapshot: Optional[Decimal] = Field(
        None,
        description="Tamaño del archivo en KB al momento del evento"
    )
    project_file_checksum_snapshot: Optional[str] = Field(
        None,
        description="Checksum del archivo al momento del evento"
    )

    # Alineado con el modelo: atributo ORM 'created_at', expuesto como 'event_created_at'
    event_created_at: datetime = Field(
        ...,
        alias="created_at",
        description="Timestamp del evento",
    )

    @field_validator("event_details", mode="before")
    @classmethod
    def parse_event_details(cls, v: Optional[Union[str, Dict[str, Any]]]) -> Optional[Union[str, Dict[str, Any]]]:
        """
        Intenta parsear JSON string a dict. Si ya es dict o None, lo regresa tal cual.
        Mantiene string si no es JSON parseable.
        """
        if v is None or isinstance(v, dict):
            return v
        if not isinstance(v, str):
            return v
        try:
            return json.loads(v)
        except (json.JSONDecodeError, ValueError):
            return v

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "project_file_event_log_id": "789e0123-b45c-67d8-e901-234567890abc",
                "project_id": "123e4567-e89b-12d3-a456-426614174000",
                "project_file_id": "456e7890-a12b-34c5-d678-901234567890",
                "project_file_id_snapshot": "456e7890-a12b-34c5-d678-901234567890",
                "user_id": "987fcdeb-51a2-43d7-b8f9-123456789abc",
                "user_email": "user@example.com",
                "event_type": "uploaded",
                "event_details": {"checksum": "abc123"},
                "project_file_name_snapshot": "documento.pdf",
                "project_file_path_snapshot": "/projects/123/documento.pdf",
                "project_file_size_kb_snapshot": "1024.50",
                "project_file_checksum_snapshot": "abc123",
                "event_created_at": "2025-10-18T10:00:00Z"
            }
        }
    )


# Variante 'lite' para listados: payload reducido (sin snapshots pesados)
class ProjectFileEventLogLite(UTF8SafeModel):
    project_file_event_log_id: UUID = Field(..., alias="id")
    project_id: UUID
    project_file_id: Optional[UUID] = None
    event_type: ProjectFileEvent
    event_details: Optional[Union[str, Dict[str, Any]]] = None
    event_created_at: datetime = Field(..., alias="created_at")

    @field_validator("event_details", mode="before")
    @classmethod
    def parse_event_details_lite(cls, v: Optional[Union[str, Dict[str, Any]]]) -> Optional[Union[str, Dict[str, Any]]]:
        if v is None or isinstance(v, dict):
            return v
        if not isinstance(v, str):
            return v
        try:
            return json.loads(v)
        except (json.JSONDecodeError, ValueError):
            return v

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "project_file_event_log_id": "789e0123-b45c-67d8-e901-234567890abc",
                "project_id": "123e4567-e89b-12d3-a456-426614174000",
                "project_file_id": "456e7890-a12b-34c5-d678-901234567890",
                "event_type": "uploaded",
                "event_details": {"stage": "ocr"},
                "event_created_at": "2025-10-18T10:00:00Z"
            }
        }
    )


# ========== QUERY SCHEMAS ==========

class ProjectFileEventLogQuery(UTF8SafeModel):
    """
    Filtros para consulta de logs de eventos de archivos.

    Alineado con ProjectQueryFacade.list_file_events() y list_file_events_seek().
    """
    project_id: UUID = Field(..., description="ID del proyecto")
    file_id: Optional[UUID] = Field(
        None,
        description="Filtrar por ID de archivo específico"
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
