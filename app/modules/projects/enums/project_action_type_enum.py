
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/enums/project_action_type_enum.py

Enum de tipos de acción realizados sobre proyectos.
Usado como tipo ENUM en PostgreSQL (project_action_type_enum).

Autor: Ixchel Beristáin
Fecha: 2025-10-23
"""

from enum import StrEnum
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM


class ProjectActionType(StrEnum):
    """
    Tipos de acción sobre proyectos.

    Valores:
    - created  : Proyecto creado
    - updated  : Proyecto actualizado (metadatos, configuración, etc.)
    - deleted  : Proyecto marcado/eliminado (según política de negocio)
    """
    # Nombres canónicos (MAYÚSCULAS) para uso en código
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"

    # Alias lowercase para compatibilidad y legibilidad
    created = "created"
    updated = "updated"
    deleted = "deleted"


def as_pg_enum(
    name: str = "project_action_type_enum",
    schema: str | None = None,
) -> PG_ENUM:
    """
    Devuelve el tipo SQLAlchemy PG_ENUM para este enum.

    Args:
        name: Nombre del tipo ENUM en PostgreSQL.
        schema: Schema de la base de datos (ej. "public").

    Returns:
        PG_ENUM configurado con ProjectActionType.
    """
    return PG_ENUM(
        ProjectActionType,
        name=name,
        schema=schema,
        create_type=False,
        values_callable=lambda x: [e.value for e in x],
    )


__all__ = ["ProjectActionType", "as_pg_enum"]
# Fin del archivo backend\app\modules\projects\enums\project_action_type_enum.py

