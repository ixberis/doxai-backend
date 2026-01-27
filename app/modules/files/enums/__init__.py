
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/enums/__init__.py

Barrel para enums del módulo Files con:
- helpers as_pg_enum (incl. alias robusto generation_method_as_pg_enum)
- aliases legacy (ProductFileGenerationMethod, Language)
- alias de miembros en ProductFileType (document/spreadsheet/presentation) sobre el Enum real

Autor: Ixchel Beristain
Fecha: 04/11/2025
"""

from __future__ import annotations

# -- Enums base + helpers as_pg_enum --
from .file_category_enum import FileCategory, FileCategoryType, as_pg_enum as file_category_as_pg_enum
from .file_type_enum import FileType, file_type_as_pg_enum
from .file_language_enum import FileLanguage, as_pg_enum as file_language_as_pg_enum
from .file_role_enum import FileRole, file_role_as_pg_enum
from .input_file_class_enum import InputFileClass, as_pg_enum as input_file_class_as_pg_enum
from .ingest_source_enum import IngestSource, as_pg_enum as ingest_source_as_pg_enum
from .product_file_event_enum import ProductFileEvent, as_pg_enum as product_file_event_as_pg_enum
from .product_file_generation_method_enum import (
    GenerationMethod,
    as_pg_enum as product_file_generation_method_as_pg_enum,
)
from .product_file_type_enum import ProductFileType, as_pg_enum as product_file_type_as_pg_enum
from .product_version_enum import ProductVersion, as_pg_enum as product_version_as_pg_enum
from .storage_backend_enum import StorageBackend, as_pg_enum as storage_backend_as_pg_enum
from .checksum_algo_enum import ChecksumAlgo, as_pg_enum as checksum_algo_as_pg_enum
from .input_processing_status_enum import InputProcessingStatus, input_processing_status_as_pg_enum
from .file_storage_state_enum import FileStorageState, as_pg_enum as file_storage_state_as_pg_enum

# -- Aliases de nombres de enums (legacy) --
ProductFileGenerationMethod = GenerationMethod
Language = FileLanguage  # schemas importan 'Language'

# -- Alias para compatibilidad con modelos que esperan generation_method_as_pg_enum --
generation_method_as_pg_enum = product_file_generation_method_as_pg_enum

# -- Aliases de miembros dentro de ProductFileType (sobre el Enum real, no proxies) --
def _alias_enum_member(enum_cls, alias_name: str, real_name: str) -> None:
    """
    Crea alias 'alias_name' -> miembro 'real_name' en un Enum real.

    Estrategia:
      1) setattr(EnumClass, alias_name, miembro_real)
      2) Inyectar en EnumClass._member_map_ tanto alias en lower como en UPPER
      3) Añadir a EnumClass._member_names_ si procede
    """
    # Si ya existe, no hacer nada
    try:
        getattr(enum_cls, alias_name)
        return
    except AttributeError:
        pass

    # Ubicar miembro real
    try:
        real_member = getattr(enum_cls, real_name)
    except Exception:
        return

    # 1) Intento directo
    try:
        setattr(enum_cls, alias_name, real_member)
    except Exception:
        pass

    # 2) Inyección en estructuras internas del EnumMeta
    try:
        mm = getattr(enum_cls, "_member_map_", None)
        if isinstance(mm, dict):
            mm[alias_name] = real_member
            up = alias_name.upper()
            mm.setdefault(up, real_member)
        mn = getattr(enum_cls, "_member_names_", None)
        if isinstance(mn, list):
            if alias_name not in mn:
                mn.append(alias_name)
            up = alias_name.upper()
            if up not in mn:
                mn.append(up)
    except Exception:
        pass

def _alias_enum_member_first(enum_cls, alias_name: str, *real_names: str) -> None:
    """
    Crea alias 'alias_name' -> primer miembro existente en real_names.
    Intenta setattr y luego inyecta en _member_map_/_member_names_.
    """
    try:
        getattr(enum_cls, alias_name)
        return
    except AttributeError:
        pass

    real_member = None
    for rn in real_names:
        try:
            real_member = getattr(enum_cls, rn)
            break
        except Exception:
            continue
    if real_member is None:
        return

    try:
        setattr(enum_cls, alias_name, real_member)
    except Exception:
        pass

    try:
        mm = getattr(enum_cls, "_member_map_", None)
        if isinstance(mm, dict):
            mm[alias_name] = real_member
            up = alias_name.upper()
            mm.setdefault(up, real_member)
        mn = getattr(enum_cls, "_member_names_", None)
        if isinstance(mn, list):
            if alias_name not in mn:
                mn.append(alias_name)
            up = alias_name.upper()
            if up not in mn:
                mn.append(up)
    except Exception:
        pass

# ⚠️ Estos apuntan a miembros que SÍ existen en tu Enum real
# - 'report' ya existe (buena aproximación a "documento")
# - 'csv' ya existe (aproximación razonable a "spreadsheet")
# - 'presentation' lo mapeamos a 'report' como fallback neutral
_alias_enum_member(ProductFileType, "document", "report")
_alias_enum_member(ProductFileType, "spreadsheet", "csv")
_alias_enum_member(ProductFileType, "presentation", "report")
_alias_enum_member(ProductFileType, "dataset", "csv")
_alias_enum_member_first(ProductFileType, "chart", "png", "report")

__all__ = [
    # enums
    "FileCategory", "FileCategoryType", "FileType", "FileLanguage", "Language", "FileRole", "InputFileClass",
    "IngestSource", "ProductFileEvent", "GenerationMethod", "ProductFileGenerationMethod",
    "ProductFileType", "ProductVersion", "StorageBackend", "ChecksumAlgo",
    "InputProcessingStatus", "FileStorageState",
    # helpers as_pg_enum
    "file_category_as_pg_enum", "file_type_as_pg_enum", "file_language_as_pg_enum",
    "file_role_as_pg_enum", "input_file_class_as_pg_enum", "ingest_source_as_pg_enum", 
    "product_file_event_as_pg_enum", "product_file_generation_method_as_pg_enum", 
    "generation_method_as_pg_enum", "product_file_type_as_pg_enum", "product_version_as_pg_enum", 
    "storage_backend_as_pg_enum", "checksum_algo_as_pg_enum", "input_processing_status_as_pg_enum",
    "file_storage_state_as_pg_enum",
]

# Fin del archivo backend\app\modules\files\enums\__init__.py