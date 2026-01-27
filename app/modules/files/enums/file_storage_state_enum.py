# -*- coding: utf-8 -*-
"""
backend/app/modules/files/enums/file_storage_state_enum.py

Enum para el estado del ciclo de vida de almacenamiento de archivos.

Valores:
- present: El archivo existe físicamente en storage
- missing: El archivo no existe en storage (ghost o eliminado por usuario)
- invalidated: El archivo fue invalidado por retención/admin

Alineación con DB:
- Corresponde a `public.file_storage_state_enum` definido en:
  database/files/01_types/01_types_core.sql

Autor: DoxAI
Fecha: 2026-01-27
"""

from __future__ import annotations

from enum import Enum

from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM


class FileStorageState(str, Enum):
    """Estado del ciclo de vida de almacenamiento de archivos."""
    
    present = "present"       # Archivo existe físicamente en storage
    missing = "missing"       # Archivo no existe en storage (ghost/eliminado por usuario)
    invalidated = "invalidated"  # Archivo invalidado por retención/admin


def as_pg_enum() -> PG_ENUM:
    """
    Retorna el tipo PG_ENUM para storage_state.
    
    Usa create_type=False porque asumimos que el enum ya existe en la BD
    (creado por DDL canónico).
    """
    return PG_ENUM(
        "present",
        "missing",
        "invalidated",
        name="file_storage_state_enum",
        create_type=False,
        schema="public",
    )


# Alias para consistencia con otros enums del módulo
file_storage_state_as_pg_enum = as_pg_enum


__all__ = [
    "FileStorageState",
    "as_pg_enum",
    "file_storage_state_as_pg_enum",
]

# Fin del archivo backend/app/modules/files/enums/file_storage_state_enum.py
