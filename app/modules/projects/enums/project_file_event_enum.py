
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/enums/project_file_event_enum.py

Enum de eventos de archivos de proyecto.
Usado como tipo ENUM en PostgreSQL (project_file_event_enum).

Autor: Ixchel Beristáin
Fecha: 2025-10-23
"""

from enum import StrEnum
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM


class ProjectFileEvent(StrEnum):
    """
    Eventos de archivos en proyectos.

    Valores:
    - uploaded   : Archivo asociado/subido al proyecto
    - validated  : Archivo validado (ej. revisión manual o automática)
    - moved      : Archivo movido (cambio de ruta lógica/carpeta)
    - deleted    : Archivo desvinculado/eliminado del proyecto
    """
    # Nombres canónicos (MAYÚSCULAS) para uso en código
    UPLOADED = "uploaded"
    VALIDATED = "validated"
    MOVED = "moved"
    DELETED = "deleted"

    # Alias lowercase para compatibilidad
    uploaded = "uploaded"
    validated = "validated"
    moved = "moved"
    deleted = "deleted"


def as_pg_enum(
    name: str = "project_file_event_enum",
    schema: str | None = None,
) -> PG_ENUM:
    """
    Devuelve el tipo SQLAlchemy PG_ENUM para este enum.

    Args:
        name: Nombre del tipo ENUM en PostgreSQL.
        schema: Schema de la base de datos (ej. "public").

    Returns:
        PG_ENUM configurado con ProjectFileEvent.
    """
    return PG_ENUM(
        ProjectFileEvent,
        name=name,
        schema=schema,
        create_type=False,
        values_callable=lambda x: [e.value for e in x],
    )


__all__ = ["ProjectFileEvent", "as_pg_enum"]
# Fin del archivo backend\app\modules\projects\enums\project_file_event_enum.py

