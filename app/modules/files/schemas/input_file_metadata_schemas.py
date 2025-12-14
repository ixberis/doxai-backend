
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/schemas/input_file_metadata_schemas.py

Schemas Pydantic v2 para metadatos técnicos de archivos INSUMO.

Incluye:
- InputFileMetadataCreate: creación inicial de metadatos.
- InputFileMetadataResponse: lectura detallada para UI u otros módulos.
- InputFileMetadataUpdate: actualización parcial (estado, checksum, error).

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.files.enums import InputProcessingStatus


class InputFileMetadataCreate(BaseModel):
    """
    Payload para registrar metadatos iniciales de un archivo insumo.
    """

    input_file_id: UUID = Field(..., description="ID del archivo insumo")
    input_file_extracted_at: Optional[str] = Field(
        default=None,
        description="Fecha/hora de extracción en formato ISO",
    )
    input_file_hash_checksum: Optional[str] = Field(
        default=None,
        description="Checksum del archivo insumo (hash calculado)",
    )
    input_file_parser_version: Optional[str] = Field(
        default=None,
        description="Versión del parser u OCR utilizado",
    )
    input_file_processing_status: Optional[InputProcessingStatus] = Field(
        default=None,
        description="Estado del procesamiento del archivo",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Mensaje de error en caso de fallo de procesamiento",
    )


class InputFileMetadataResponse(BaseModel):
    """
    Representación completa de los metadatos de un archivo insumo.
    """

    model_config = ConfigDict(from_attributes=True)

    input_file_metadata_id: UUID = Field(..., description="ID de los metadatos")
    input_file_id: UUID = Field(..., description="ID del archivo insumo")
    input_file_extracted_at: Optional[str] = Field(
        default=None,
        description="Fecha/hora de extracción en formato ISO",
    )
    input_file_hash_checksum: Optional[str] = Field(
        default=None,
        description="Checksum del archivo insumo",
    )
    input_file_parser_version: Optional[str] = Field(
        default=None,
        description="Versión del parser u OCR utilizado",
    )
    input_file_processing_status: Optional[InputProcessingStatus] = Field(
        default=None,
        description="Estado del procesamiento asociado al archivo",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Mensaje de error en caso de fallo",
    )
    extracted_at: Optional[datetime] = Field(
        default=None,
        description="Fecha/hora en que se extrajo contenido del insumo",
    )
    processed_at: Optional[datetime] = Field(
        default=None,
        description="Fecha/hora en que concluyó el pipeline posterior",
    )
    validation_status: Optional[InputProcessingStatus] = Field(
        default=None,
        description="Estado del procesamiento asociado al archivo",
    )


class InputFileMetadataUpdate(BaseModel):
    """
    Actualización parcial de metadatos del archivo insumo.
    """

    parser_version: Optional[str] = Field(
        default=None,
        description="Versión del parser usado",
    )
    hash_checksum: Optional[str] = Field(
        default=None,
        description="Checksum del archivo insumo",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Mensaje de error durante el procesamiento",
    )
    validation_status: Optional[InputProcessingStatus] = Field(
        default=None,
        description="Estado del procesamiento",
    )


__all__ = [
    "InputFileMetadataCreate",
    "InputFileMetadataResponse",
    "InputFileMetadataUpdate",
]

# Fin del archivo backend/app/modules/files/schemas/input_file_metadata_schemas.py







