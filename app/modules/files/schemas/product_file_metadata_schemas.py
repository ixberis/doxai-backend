
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/schemas/product_file_metadata_schemas.py

Schemas Pydantic v2 para metadatos enriquecidos de archivos PRODUCTO.

Incluye:
- ProductFileMetadataCreate: creación/registro de metadatos.
- ProductFileMetadataRead: lectura detallada para UI y auditoría.
- ProductFileReviewUpdate: actualización parcial durante revisión/aprobación.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.files.enums import (
    GenerationMethod,
    ChecksumAlgo,
)


class ProductFileMetadataBase(BaseModel):
    """
    Schema base para metadatos de producto, usado por tests legacy.
    """

    model_config = ConfigDict(from_attributes=True)

    product_file_hash_checksum: Optional[str] = Field(
        default=None,
        description="Hash de checksum del archivo",
    )
    checksum_algo: Optional[str] = Field(
        default=None,
        description="Algoritmo usado para checksum",
    )
    product_file_generation_method: GenerationMethod = Field(
        ...,
        description="Método de generación del archivo",
    )
    generation_params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Parámetros de generación",
    )
    product_file_extracted_at: Optional[str] = Field(
        default=None,
        description="Fecha/hora de extracción (ISO format)",
    )
    product_file_ragmodel_version_used: Optional[str] = Field(
        default=None,
        description="Versión del modelo RAG",
    )


class ProductFileMetadataResponse(ProductFileMetadataBase):
    """
    Schema de respuesta para metadatos de producto, usado por tests legacy.
    """

    product_file_metadata_id: str = Field(..., description="ID de metadatos")
    product_file_id: str = Field(..., description="ID del archivo producto")


class ProductFileMetadataCreate(BaseModel):
    """
    Payload para registrar metadatos de un archivo producto.
    """

    product_file_id: UUID = Field(..., description="ID del archivo producto")
    generation_method: GenerationMethod = Field(
        ...,
        description="Método o pipeline con el que se generó el archivo",
    )
    generation_params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Parámetros usados para generar el archivo (prompt, filtros, etc.)",
    )
    ragmodel_version_used: Optional[str] = Field(
        default=None,
        description="Versión del modelo RAG u otro modelo asociado",
    )


class ProductFileMetadataRead(BaseModel):
    """
    Representación completa de los metadatos de un archivo producto.
    """

    model_config = ConfigDict(from_attributes=True)

    product_file_id: UUID = Field(..., description="ID del archivo producto")
    generation_method: GenerationMethod = Field(
        ...,
        description="Método o pipeline con el que se generó el archivo",
    )
    generation_params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Parámetros usados para generar el archivo",
    )
    ragmodel_version_used: Optional[str] = Field(
        default=None,
        description="Versión del modelo asociado",
    )

    page_count: Optional[int] = Field(
        default=None,
        ge=0,
        description="Número de páginas del archivo, si aplica",
    )
    word_count: Optional[int] = Field(
        default=None,
        ge=0,
        description="Número aproximado de palabras",
    )

    keywords: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Palabras clave extraídas o asignadas",
    )
    entities: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Entidades extraídas (por ejemplo, NER)",
    )
    sections: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Estructura de secciones detectadas",
    )
    summary: Optional[str] = Field(
        default=None,
        description="Resumen textual del contenido",
    )

    checksum_algo: Optional[ChecksumAlgo] = Field(
        default=None,
        description="Algoritmo de checksum usado",
    )
    checksum: Optional[str] = Field(
        default=None,
        description="Valor del checksum",
    )

    extracted_at: Optional[datetime] = Field(
        default=None,
        description="Fecha/hora de extracción de contenido para metadatos",
    )

    approved_by: Optional[UUID] = Field(
        default=None,
        description="Usuario que aprobó el artefacto, si aplica",
    )
    approved_at: Optional[datetime] = Field(
        default=None,
        description="Fecha/hora de aprobación",
    )
    review_notes: Optional[str] = Field(
        default=None,
        description="Notas o comentarios de revisión",
    )


class ProductFileReviewUpdate(BaseModel):
    """
    Actualización parcial durante el proceso de revisión/aprobación.
    """

    approved_by: Optional[UUID] = Field(
        default=None,
        description="Usuario que aprueba o desaprueba el artefacto",
    )
    approved_at: Optional[datetime] = Field(
        default=None,
        description="Fecha/hora de aprobación",
    )
    review_notes: Optional[str] = Field(
        default=None,
        description="Notas de revisión",
    )


__all__ = [
    "ProductFileMetadataBase",
    "ProductFileMetadataResponse",
    "ProductFileMetadataCreate",
    "ProductFileMetadataRead",
    "ProductFileReviewUpdate",
]

# Fin del archivo backend/app/modules/files/schemas/product_file_metadata_schemas.py
