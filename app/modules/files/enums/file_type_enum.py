
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/enums/file_type_enum.py

Enum de tipos de archivo (formato físico) en DoxAI.

Alineación con DB (file_type_enum):
Incluye documentos, hojas de cálculo, texto, medios, contenedores y formatos web.
Valores en minúsculas; se mantienen alias legacy en MAYÚSCULAS para compatibilidad.

Autor: Ixchel Beristáin
Fecha: 2025-11-10
"""

from __future__ import annotations
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy import TypeDecorator

from .compat_base import _StrEnum, EnumMixin


class FileType(EnumMixin, _StrEnum):
    # Documentos y texto
    pdf = "pdf"
    docx = "docx"
    xlsx = "xlsx"
    pptx = "pptx"
    txt = "txt"
    csv = "csv"
    md = "md"
    rtf = "rtf"
    html = "html"
    json = "json"
    xml = "xml"

    # Medios y contenedores
    image = "image"
    video = "video"
    audio = "audio"
    zip = "zip"

    # Aliases semánticos comunes
    document = pdf  # alias para document (mapea a PDF por defecto)

    # Aliases legacy y compatibilidad
    PDF = pdf
    DOCUMENT = document
    DOCX = docx
    XLSX = xlsx
    PPTX = pptx
    TXT = txt
    TEXT = txt
    CSV = csv
    MD = md
    RTF = rtf
    HTML = html
    JSON = json
    XML = xml
    IMAGE = image
    VIDEO = video
    AUDIO = audio
    ZIP = zip


# Valores canónicos (sin aliases) para PostgreSQL
_FILE_TYPE_VALUES = [
    "pdf", "docx", "xlsx", "pptx", "txt", "csv", "md", "rtf",
    "html", "json", "xml", "image", "video", "audio", "zip"
]


class FileTypeType(TypeDecorator):
    """
    TypeDecorator que convierte FileType enum a string para PostgreSQL.
    Resuelve el problema de StrEnum con aliases que SQLAlchemy no maneja correctamente.
    """
    impl = PG_ENUM(*_FILE_TYPE_VALUES, name="file_type_enum", create_type=False)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, FileType):
            return value.value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return FileType(value)


def file_type_as_pg_enum(name: str = "file_type_enum") -> FileTypeType:
    """
    Devuelve el TypeDecorator para FileType.
    """
    return FileTypeType()


__all__ = ["FileType", "FileTypeType", "file_type_as_pg_enum"]

# Fin del archivo backend/app/modules/files/enums/file_type_enum.py
