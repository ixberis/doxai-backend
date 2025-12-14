
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/schemas/product_file_schemas.py

Schemas Pydantic v2 para archivos PRODUCTO generados por DoxAI.

Incluye:
- ProductFileCreate: payload para crear un archivo producto.
- ProductFileResponse: representación canónica para respuestas de la API.
- ProjectFileUnionResponse: vista unificada por proyecto (input/product).

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.files.enums import (
    FileLanguage,
    ProductFileType,
    ProductVersion,
    StorageBackend,
    FileCategory,
)


class ProductFileCreate(BaseModel):
    """
    Payload para registrar un nuevo archivo producto.

    Normalmente se usa desde facades/servicios que generan artefactos
    (reportes, exports, documentos procesados).
    """

    model_config = ConfigDict(populate_by_name=True)

    project_id: UUID = Field(..., description="Proyecto al que pertenece el archivo producto")
    
    product_file_name: str = Field(
        ...,
        description="Nombre original con el que se guardará el archivo",
    )
    product_file_display_name: Optional[str] = Field(
        default=None,
        description="Nombre legible para UI",
    )
    product_file_mime_type: str = Field(
        ...,
        description="Tipo MIME del archivo producto",
    )
    product_file_size_bytes: int = Field(
        ...,
        ge=0,
        description="Tamaño del archivo en bytes",
    )

    product_file_type: ProductFileType = Field(
        ...,
        description="Tipo lógico de archivo producto",
    )
    product_file_version: ProductVersion = Field(
        default=ProductVersion.v1,
        description="Versión de artefacto (v1, v2, etc.)",
    )
    product_file_language: Optional[FileLanguage] = Field(
        default=None,
        description="Idioma principal del archivo producto",
    )

    product_file_storage_backend: StorageBackend = Field(
        default=StorageBackend.supabase,
        description="Backend de almacenamiento utilizado",
    )
    product_file_storage_path: str = Field(
        ...,
        description="Ruta o key del archivo en el storage",
    )
    
    product_file_category: Optional[FileCategory] = Field(
        default=None,
        description="Categoría del archivo producto",
    )

    generated_by: UUID = Field(
        default_factory=uuid4,
        description="Usuario (o servicio) que generó el archivo (default: UUID aleatorio si no se proporciona)",
    )


class ProductFileResponse(BaseModel):
    """
    Representación canónica de un archivo producto en respuestas de la API.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    product_file_id: UUID = Field(..., description="ID del archivo producto")
    file_id: Optional[UUID] = Field(
        default=None,
        description="ID canónico en files_base, si está asignado",
    )

    project_id: UUID = Field(..., description="Proyecto al que pertenece el archivo")
    
    original_name: Optional[str] = Field(
        default=None,
        alias="product_file_original_name",
        description="Nombre original del archivo",
    )
    display_name: Optional[str] = Field(
        default=None,
        alias="product_file_display_name",
        description="Nombre legible para UI",
    )

    mime_type: str = Field(
        ...,
        alias="product_file_mime_type",
        description="Tipo MIME",
    )
    extension: Optional[str] = Field(
        default=None,
        alias="product_file_extension",
        description="Extensión del archivo",
    )
    
    @property
    def name(self) -> str:
        """Nombre del archivo (display_name o original_name)."""
        return self.display_name or self.original_name
    
    @property
    def product_file_name(self) -> str:
        """Alias para name."""
        return self.name
    
    @property
    def size_bytes(self) -> int:
        """Tamaño del archivo en bytes desde el modelo ORM."""
        # El modelo ORM usa product_file_size_bytes
        return getattr(self, 'product_file_size_bytes', 0)
    
    @property
    def product_file_size(self) -> int:
        """Property alias backward compatible."""
        return self.size_bytes

    product_file_size_bytes: int = Field(
        default=0,
        ge=0,
        alias="product_file_size",
        description="Tamaño del archivo en bytes (columna ORM)",
    )

    file_type: ProductFileType = Field(
        ...,
        alias="product_file_type",
        description="Tipo lógico de archivo producto",
    )
    version: ProductVersion = Field(
        ...,
        alias="product_file_version",
        description="Versión del artefacto",
    )
    language: Optional[FileLanguage] = Field(
        default=None,
        alias="product_file_language",
        description="Idioma principal",
    )

    storage_backend: StorageBackend = Field(
        ...,
        alias="product_file_storage_backend",
        description="Backend de almacenamiento",
    )
    storage_path: str = Field(
        ...,
        alias="product_file_storage_path",
        description="Ruta clave de almacenamiento",
    )
    
    category: Optional[FileCategory] = Field(
        default=None,
        alias="product_file_category",
        description="Categoría del archivo producto",
    )

    generated_by: UUID = Field(
        default_factory=uuid4,
        alias="product_file_generated_by",
        description="Usuario o servicio que generó el archivo",
    )
    is_active: bool = Field(
        default=True,
        alias="product_file_is_active",
        description="Indica si el archivo está activo",
    )
    is_archived: bool = Field(
        default=False,
        alias="product_file_is_archived",
        description="Indica si el archivo está archivado",
    )
    generated_at: datetime = Field(
        ...,
        alias="product_file_generated_at",
        description="Fecha/hora de generación del archivo",
    )


class ProjectFileUnionResponse(BaseModel):
    """
    Vista unificada de archivos (insumos y productos) por proyecto.

    Se construye típicamente a partir de vistas SQL tipo `view_project_files_union`
    y sirve para UI donde se muestra una tabla única de archivos del proyecto.
    """

    model_config = ConfigDict(from_attributes=True)

    file_id: UUID = Field(..., description="ID canónico en files_base")
    project_id: UUID = Field(..., description="Proyecto al que pertenece el archivo")

    role: str = Field(..., description="Rol lógico del archivo ('input' o 'product')")
    category: Optional[FileCategory] = Field(
        default=None,
        description="Categoría del archivo, cuando aplique",
    )

    original_name: str = Field(..., description="Nombre original del archivo")
    display_name: Optional[str] = Field(
        default=None,
        description="Nombre legible para UI",
    )

    mime_type: str = Field(..., description="Tipo MIME")
    size_bytes: int = Field(..., ge=0, description="Tamaño del archivo en bytes")

    created_at: datetime = Field(..., description="Fecha/hora de creación/carga del archivo")


__all__ = [
    "ProductFileCreate",
    "ProductFileResponse",
    "ProjectFileUnionResponse",
]

# Fin del archivo backend/app/modules/files/schemas/product_file_schemas.py








