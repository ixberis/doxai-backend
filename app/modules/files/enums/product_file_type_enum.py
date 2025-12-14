# -*- coding: utf-8 -*-
"""
backend/app/modules/files/enums/product_file_type_enum.py

Enum de tipos de archivo de producto (tipo lógico de resultado) en DoxAI.
Incluye descargables y artefactos internos RAG.
Valores en minúsculas con aliases legacy en MAYÚSCULAS.

Autor: Ixchel Beristáin
Fecha: 2025-10-23
Actualización: 2025-11-05 (image/audio/video; alias archive -> zip; alias document -> report; agrega other)
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

from .compat_base import _StrEnum, EnumMixin


class ProductFileType(EnumMixin, _StrEnum):
    # Descargables
    zip      = "zip"
    report   = "report"
    csv      = "csv"
    json     = "json"
    proposal = "proposal"
    matrix   = "matrix"
    image    = "image"
    video    = "video"
    audio    = "audio"
    other    = "other"
    
    # Tipos adicionales
    presentation = "presentation"
    spreadsheet = "spreadsheet"
    dataset = "dataset"
    chart = "chart"

    # Aliases semánticos
    archive  = zip       # contenedores comprimidos
    document = report    # documentos de lectura

    # Artefactos internos RAG
    markdown             = "markdown"
    tables_json          = "tables_json"
    semantic_chunks_json = "semantic_chunks_json"
    forms_json           = "forms_json"

    # Aliases legacy
    ZIP = zip
    REPORT = report
    CSV = csv
    JSON = json
    PROPOSAL = proposal
    MATRIX = matrix
    IMAGE = image
    VIDEO = video
    AUDIO = audio
    OTHER = other
    ARCHIVE = archive
    DOCUMENT = document
    MARKDOWN = markdown
    TABLES_JSON = tables_json
    SEMANTIC_CHUNKS_JSON = semantic_chunks_json
    FORMS_JSON = forms_json
    PRESENTATION = presentation
    SPREADSHEET = spreadsheet
    DATASET = dataset
    CHART = chart


def as_pg_enum(name: str = "product_file_type_enum", native_enum: bool = False) -> PG_ENUM:
    return PG_ENUM(
        ProductFileType,
        name=name,
        create_type=False,
        values_callable=lambda x: [e.value for e in x],
    )


__all__ = ["ProductFileType", "as_pg_enum"]

# Fin del archivo backend\app\modules\files\enums\product_file_type_enum.py
