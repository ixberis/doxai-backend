
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/repositories/project_file_repository.py

Repositorio para acceso a datos de archivos de proyecto (ProjectFile).

Esta tabla es parte del diseño Projects 2.0 como "vista lógica" de archivos
asociados a un proyecto. La fuente canónica de archivos físicos es el módulo
Files (input/product), pero ProjectFile permite mantener metadatos y vínculos
a nivel de proyecto.

Autor: Ixchel Beristáin
Fecha: 2025-11-21
"""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.modules.projects.models import ProjectFile


def get_project_file_by_id(
    db: Session,
    project_file_id: UUID,
) -> Optional[ProjectFile]:
    """
    Obtiene un archivo de proyecto por su ID.
    """
    return (
        db.query(ProjectFile)
        .filter(ProjectFile.id == project_file_id)
        .first()
    )


def list_project_files(
    db: Session,
    project_id: UUID,
) -> List[ProjectFile]:
    """
    Lista archivos asociados a un proyecto, ordenados por fecha de creación.
    """
    q = (
        db.query(ProjectFile)
        .filter(ProjectFile.project_id == project_id)
        .order_by(desc(ProjectFile.created_at))
    )
    return list(q.all())


def save_project_file(
    db: Session,
    project_file: ProjectFile,
) -> ProjectFile:
    """
    Persiste un archivo de proyecto (insert/update).
    """
    db.add(project_file)
    db.flush()
    db.commit()
    db.refresh(project_file)
    return project_file


def delete_project_file(
    db: Session,
    project_file: ProjectFile,
) -> None:
    """
    Elimina un archivo de proyecto.
    La política (borrado lógico/físico) se controla en la capa de servicios.
    """
    db.delete(project_file)
    db.commit()


__all__ = [
    "get_project_file_by_id",
    "list_project_files",
    "save_project_file",
    "delete_project_file",
]

# Fin del archivo backend/app/modules/projects/repositories/project_file_repository.py