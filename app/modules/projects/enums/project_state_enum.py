
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/enums/project_state_enum.py

Enum: project_state_enum
Estados del ciclo de vida operativo/técnico de un proyecto en DoxAI.

Valores: ('created', 'uploading', 'processing', 'ready', 'error', 'archived')

⚠️ DISTINCIÓN SEMÁNTICA:
- ProjectState: Estados del ciclo de vida técnico/operativo del proyecto.
  Ejemplo: "archived" = conservación histórica/readonly, fin del ciclo operativo.

- ProjectStatus (project_status_enum): Situación administrativa/de negocio.
  Ejemplo: "in_process" = actividad administrativa activa (contratos/facturas).

📋 REGLA ANTI-SOLAPE:
- Nuevos valores de flujo operativo → ProjectState
- Nuevos valores de situación de negocio → ProjectStatus
- Validar que no exista equivalente antes de agregar.

Autor: Ixchel Beristáin
Fecha: 2025-10-23
"""

from enum import StrEnum
from sqlalchemy import TypeDecorator
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM


class ProjectState(StrEnum):
    """
    Estados del ciclo de vida operativo de un proyecto.

    Valores:
    - created   : Proyecto recién creado
    - uploading : Archivos en proceso de carga
    - processing: Procesamiento de datos en curso
    - ready     : Listo para uso/consulta
    - error     : Error en procesamiento
    - archived  : Conservación histórica/readonly (fin del ciclo operativo)

    Nota: 'archived' indica fin del ciclo de vida técnico,
    no implica necesariamente cierre administrativo.
    Para situación de negocio, ver ProjectStatus (project_status_enum).
    """
    # Valores canónicos que esperan los tests
    CREATED = "created"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"
    ARCHIVED = "archived"

    # Alias lowercase para compatibilidad
    created = "created"
    uploading = "uploading"
    processing = "processing"
    ready = "ready"
    error = "error"
    archived = "archived"


class ProjectStateType(TypeDecorator):
    """
    TypeDecorator para mapear ProjectState ↔ PostgreSQL project_state_enum.
    
    Convierte:
    - Python → DB: ProjectState.CREATED → "created" (string)
    - DB → Python: "created" → ProjectState.CREATED (enum)
    """
    impl = PG_ENUM(
        "created", "uploading", "processing", "ready", "error", "archived",
        name="project_state_enum",
        create_type=False,
    )
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Convierte Python enum a string para INSERT/UPDATE."""
        if value is None:
            return None
        if isinstance(value, ProjectState):
            return value.value  # "created", "uploading", etc.
        return str(value)

    def process_result_value(self, value, dialect):
        """Convierte string de DB a Python enum para SELECT."""
        if value is None:
            return None
        return ProjectState(value)


def as_pg_enum(
    name: str = "project_state_enum",
    schema: str | None = None,
) -> ProjectStateType:
    """
    Devuelve el tipo SQLAlchemy TypeDecorator para este enum,
    mapeado 1:1 al tipo ya existente en Postgres.

    Args:
        name: Nombre del tipo ENUM en PostgreSQL (ignorado, usa default).
        schema: Schema de la base de datos (ignorado en TypeDecorator).

    Returns:
        ProjectStateType configurado.
    """
    return ProjectStateType()


__all__ = ["ProjectState", "ProjectStateType", "as_pg_enum"]
# Fin del archivo backend\app\modules\projects\enums\project_state_enum.py
