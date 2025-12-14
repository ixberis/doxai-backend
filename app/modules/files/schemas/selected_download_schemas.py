
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/schemas/selected_download_schemas.py

Schemas Pydantic v2 para descarga selectiva de archivos.

Incluye:
- SelectedFilesDownloadRequest: lista de file_ids a incluir en un ZIP.
- PartialDownloadResponse: resumen de éxito/fallo por archivo.

Autor: DoxAI / Ajustes Files v2 por Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SelectedFilesDownloadRequest(BaseModel):
    """
    Solicitud de descarga selectiva de archivos (por file_id canónico).
    """

    project_id: UUID = Field(..., description="Proyecto al que pertenecen los archivos")
    file_ids: List[UUID] = Field(
        ...,
        min_length=1,
        description="Lista de IDs canónicos de archivos a incluir en la descarga",
    )


class PartialDownloadResponseItem(BaseModel):
    """
    Resultado individual para cada archivo solicitado en una descarga parcial.
    """

    model_config = ConfigDict(from_attributes=True)

    file_id: UUID = Field(..., description="ID canónico del archivo")
    file_name: str = Field(..., description="Nombre del archivo")
    status: str = Field(..., description="Estado del archivo en la descarga (ok/missing/error)")
    reason: Optional[str] = Field(
        default=None,
        description="Detalle adicional en caso de error o ausencia",
    )


class PartialDownloadResponse(BaseModel):
    """
    Resumen de la operación de descarga selectiva.

    Permite a la UI informar claramente qué archivos se descargaron,
    cuáles no y por qué.
    """

    downloaded: List[PartialDownloadResponseItem] = Field(
        default_factory=list,
        description="Archivos descargados exitosamente",
    )
    missing: List[PartialDownloadResponseItem] = Field(
        default_factory=list,
        description="Archivos que no se encontraron o no se pudieron descargar",
    )

    total_requested: int = Field(
        ...,
        ge=0,
        description="Total de archivos solicitados",
    )
    success_count: int = Field(
        ...,
        ge=0,
        description="Cantidad de archivos descargados",
    )
    missing_count: int = Field(
        ...,
        ge=0,
        description="Cantidad de archivos no encontrados",
    )


__all__ = [
    "SelectedFilesDownloadRequest",
    "PartialDownloadResponseItem",
    "PartialDownloadResponse",
]

# Fin del archivo backend/app/modules/files/schemas/selected_download_schemas.py
