
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/enums/file_role_enum.py

Enum del rol lógico de archivo en el módulo Files de DoxAI.

Alineación con DB:
- Mapea directamente al tipo ENUM de PostgreSQL `file_role_enum`.
- Se utiliza para distinguir si un registro lógico representa un archivo
  INSUMO ("input") o un archivo PRODUCTO ("product"), tal como se define
  en la tabla `files_base` del esquema SQL.

Uso previsto:
- Como tipo fuerte en modelos y servicios relacionados con la tabla base
  de archivos.
- Para construir el ENUM de SQLAlchemy vía `file_role_as_pg_enum` cuando
  se necesite mapear la columna al tipo nativo de PostgreSQL.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from enum import Enum

from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM


class FileRole(str, Enum):
    """
    Rol lógico de un archivo en el módulo Files.

    Valores:
        - input:  Archivo insumo subido por el usuario.
        - product: Archivo producto generado por DoxAI (p. ej. reportes, exports).
    """

    INPUT = "input"
    PRODUCT = "product"


def file_role_as_pg_enum(name: str = "file_role_enum") -> PG_ENUM:
    """
    Devuelve el ENUM de SQLAlchemy vinculado a FileRole.

    Parámetros
    ----------
    name:
        Nombre del tipo ENUM en PostgreSQL. Por defecto `file_role_enum`,
        alineado con la definición en `01_types/02_enums_files_roles.sql`.

    Retorna
    -------
    sqlalchemy.dialects.postgresql.ENUM
        Tipo ENUM de SQLAlchemy configurado para usar los valores de FileRole
        sin crear el tipo en la base de datos (create_type=False), asumiendo
        que ya fue creado por los scripts SQL.
    """
    return PG_ENUM(
        FileRole,
        name=name,
        create_type=False,
        values_callable=lambda enum_cls: [member.value for member in enum_cls],
    )


__all__ = ["FileRole", "file_role_as_pg_enum"]

# Fin del archivo backend/app/modules/files/enums/file_role_enum.py