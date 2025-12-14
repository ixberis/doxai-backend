
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/schemas/input_file_schemas.py

Schemas Pydantic v2 para representar archivos INSUMO en el módulo Files.

Incluye:
- InputFileUpload: payload de creación/carga de archivo insumo.
- InputFileUpdate: actualización parcial de atributos lógicos.
- InputFileResponse: representación canónica para respuestas de la API.
- InputFileCreate: alias de InputFileUpload para compatibilidad interna.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.files.enums import (
    FileType,
    FileCategory,
    FileLanguage,
    Language,
    InputFileClass,
    IngestSource,
    InputProcessingStatus,
    StorageBackend,
)


class InputFileUpload(BaseModel):
    """
    Datos necesarios para registrar un archivo insumo.

    Normalmente se combina con el fichero binario recibido vía UploadFile
    en el ruteador.
    """

    project_id: UUID = Field(..., description="ID del proyecto al que pertenece el archivo")
    original_name: str = Field(..., description="Nombre original del archivo al momento de la carga")
    display_name: Optional[str] = Field(
        None,
        description="Nombre legible para mostrar en UI (si difiere del original)",
    )
    mime_type: str = Field(..., description="Tipo MIME reportado para el archivo")
    size_bytes: int = Field(..., ge=0, description="Tamaño del archivo en bytes")

    file_type: FileType = Field(..., description="Tipo lógico de archivo (document, spreadsheet, etc.)")
    file_category: FileCategory = Field(
        default=FileCategory.input,
        description="Categoría lógica del archivo (en insumos siempre 'input')",
    )
    ingest_source: IngestSource = Field(
        default=IngestSource.upload,
        description="Fuente de ingesta del archivo (upload, api, sync, etc.)",
    )
    language: Optional[Language] = Field(
        default=None,
        description="Idioma principal del contenido, si se conoce",
    )
    input_file_class: InputFileClass = Field(
        default=InputFileClass.source,
        description="Clase lógica del archivo insumo (source, reference, etc.)",
    )


class InputFileUpdate(BaseModel):
    """
    Actualización parcial de atributos del archivo insumo.

    Se usa típicamente en endpoints PATCH.
    """

    display_name: Optional[str] = Field(
        default=None,
        description="Nuevo nombre legible para mostrar en UI",
    )
    language: Optional[Language] = Field(
        default=None,
        description="Idioma principal del contenido, si se desea actualizar",
    )
    input_file_class: Optional[InputFileClass] = Field(
        default=None,
        description="Clase lógica del archivo insumo",
    )
    is_archived: Optional[bool] = Field(
        default=None,
        description="Marca el archivo como archivado/no-archivado",
    )


class InputFileResponse(BaseModel):
    """
    Representación canónica de un archivo insumo en respuestas de la API.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    
    @model_validator(mode='before')
    @classmethod
    def handle_size_alias(cls, data):
        """Maneja alias backward compatible para tamaño del archivo."""
        if isinstance(data, dict):
            # Si viene input_file_size pero no size_bytes, usar input_file_size
            if 'input_file_size' in data and 'size_bytes' not in data:
                data['size_bytes'] = data['input_file_size']
            # Similar para input_file_size_bytes
            if 'input_file_size_bytes' in data and 'size_bytes' not in data:
                data['size_bytes'] = data['input_file_size_bytes']
        return data

    input_file_id: UUID = Field(..., description="Identificador único del archivo insumo")
    file_id: Optional[UUID] = Field(
        default=None,
        description="Identificador canónico en files_base, si está asignado",
    )

    project_id: UUID = Field(..., description="Proyecto al que pertenece el archivo")
    user_email: Optional[str] = Field(
        default=None,
        description="Email del usuario que subió el archivo",
    )
    uploaded_by: UUID = Field(
        ...,
        alias="input_file_uploaded_by",
        description="Usuario que subió el archivo",
    )

    original_name: str = Field(
        ...,
        alias="input_file_original_name",
        description="Nombre original del archivo",
    )
    display_name: Optional[str] = Field(
        default=None,
        alias="input_file_display_name",
        description="Nombre legible para mostrar en UI",
    )
    
    @property
    def name(self) -> str:
        """Nombre del archivo (display_name o fallback a original_name)."""
        return self.display_name or self.original_name

    mime_type: str = Field(
        ...,
        alias="input_file_mime_type",
        description="Tipo MIME",
    )
    extension: Optional[str] = Field(
        default=None, 
        alias="input_file_extension",
        description="Extensión del archivo (sin punto)",
    )

    size_bytes: int = Field(
        ...,
        ge=0,
        description="Tamaño del archivo en bytes",
    )
    
    @property
    def input_file_size_bytes(self) -> int:
        """Property alias para tests que acceden directamente."""
        return self.size_bytes
    
    @property  
    def input_file_size(self) -> int:
        """Property alias backward compatible."""
        return self.size_bytes

    file_type: FileType = Field(
        ...,
        alias="input_file_type",
        description="Tipo lógico del archivo",
    )
    file_category: FileCategory = Field(
        ...,
        alias="input_file_category",
        description="Categoría del archivo (en insumos 'input')",
    )
    input_file_class: InputFileClass = Field(
        ...,
        description="Clase lógica del archivo insumo",
    )
    language: Optional[FileLanguage] = Field(
        default=None,
        alias="input_file_language",
        description="Idioma detectado u asignado al archivo",
    )

    ingest_source: IngestSource = Field(
        default=IngestSource.upload,
        alias="input_file_ingest_source",
        description="Fuente de ingesta del archivo (default: upload)",
    )
    storage_backend: StorageBackend = Field(
        default=StorageBackend.supabase,
        alias="input_file_storage_backend",
        description="Backend de almacenamiento usado (default: supabase)",
    )
    storage_path: str = Field(
        ...,
        alias="input_file_storage_path",
        description="Ruta/cadena para ubicar el archivo en el storage",
    )

    status: InputProcessingStatus = Field(
        default=InputProcessingStatus.uploaded,
        alias="input_file_status",
        description="Estado del pipeline de procesamiento (default: uploaded)",
    )
    
    @property
    def processing_status(self) -> InputProcessingStatus:
        """Alias para status del procesamiento."""
        return self.status

    is_active: bool = Field(
        ...,
        alias="input_file_is_active",
        description="Indica si el archivo está activo",
    )
    is_archived: bool = Field(
        ...,
        alias="input_file_is_archived",
        description="Indica si el archivo está archivado",
    )
    uploaded_at: datetime = Field(
        ...,
        alias="input_file_uploaded_at",
        description="Fecha/hora de carga del archivo",
    )


# Alias para compatibilidad interna
class InputFileCreate(BaseModel):
    """
    Alias interno para creación de archivos insumo.

    Se mantiene por compatibilidad con partes del código que
    referencian `InputFileCreate` en vez de `InputFileUpload`.
    """

    file_name: str = Field(..., description="Nombre del archivo")
    file_type: FileType = Field(..., description="Tipo lógico de archivo")
    mime_type: str = Field(..., description="Tipo MIME")
    size_bytes: int = Field(..., ge=0, description="Tamaño en bytes")
    storage_backend: str = Field(..., description="Backend de storage")
    storage_path: str = Field(..., description="Ruta de almacenamiento")


__all__ = [
    "InputFileUpload",
    "InputFileUpdate",
    "InputFileResponse",
    "InputFileCreate",
]

# Fin del archivo backend/app/modules/files/schemas/input_file_schemas.py

