
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/enums/project_status_enum.py

Enum de estado administrativo/de negocio del proyecto.
Usado como tipo ENUM en PostgreSQL (project_status_enum).

⚠️ DISTINCIÓN SEMÁNTICA:
- ProjectStatus: Situación administrativa/de negocio (contratos, facturas, entregables).
  Ejemplo: "in_process" indica que hay actividad administrativa activa.

- ProjectState (project_state_enum): Estado del ciclo de vida técnico/operativo.
  Ejemplo: "archived" indica conservación histórica/readonly del ciclo operativo.

📋 REGLA ANTI-SOLAPE:
- Nuevos valores de flujo operativo → ProjectState (project_state_enum)
- Nuevos valores de situación de negocio → ProjectStatus (project_status_enum)
- Antes de agregar un valor, validar que no exista equivalente en el otro enum.

Autor: Ixchel Beristáin
Fecha: 2025-10-23
"""

from enum import StrEnum
from sqlalchemy import TypeDecorator
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM


class ProjectStatus(StrEnum):
    """
    Estados administrativos/de negocio de un proyecto.

    Valores:
    - in_process / IN_PROCESS: Proyecto con actividad administrativa activa
      (contratos, pagos, entregas).
    - IN_PROGRESS: Alias de in_process para compatibilidad.
    """
    IN_PROCESS = "in_process"   # Valor canónico que esperan los tests
    IN_PROGRESS = "in_process"  # Alias compatible
    in_process = "in_process"   # Alias lowercase


class ProjectStatusType(TypeDecorator):
    """
    TypeDecorator para mapear ProjectStatus ↔ PostgreSQL project_status_enum.
    
    Convierte:
    - Python → DB: ProjectStatus.IN_PROCESS → "in_process" (string)
    - DB → Python: "in_process" → ProjectStatus.IN_PROCESS (enum)
    """
    impl = PG_ENUM(
        "in_process",
        name="project_status_enum",
        create_type=False,
    )
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Convierte Python enum a string para INSERT/UPDATE."""
        if value is None:
            return None
        if isinstance(value, ProjectStatus):
            return value.value  # "in_process"
        return str(value)

    def process_result_value(self, value, dialect):
        """Convierte string de DB a Python enum para SELECT."""
        if value is None:
            return None
        return ProjectStatus(value)


def as_pg_enum(
    name: str = "project_status_enum",
    schema: str | None = None,
) -> ProjectStatusType:
    """
    Devuelve el tipo SQLAlchemy TypeDecorator para este enum.

    Args:
        name: Nombre del tipo ENUM en PostgreSQL (ignorado, usa default).
        schema: Schema de la base de datos (ignorado en TypeDecorator).

    Returns:
        ProjectStatusType configurado.
    """
    return ProjectStatusType()


__all__ = ["ProjectStatus", "ProjectStatusType", "as_pg_enum"]
# Fin del archivo backend\app\modules\projects\enums\project_status_enum.py
