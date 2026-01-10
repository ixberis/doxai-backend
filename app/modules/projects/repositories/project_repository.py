
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/repositories/project_repository.py

Repositorio para acceso a datos de proyectos (Project).

Responsabilidades:
- Lecturas básicas (por id, slug, usuario)
- Listados paginados por usuario
- Persistencia simple (save/delete)

La lógica de negocio (validaciones, generación de slug, cambios de estado)
permanece en los servicios/facades, no en el repositorio.

Autor: Ixchel Beristáin
Fecha: 2025-11-21
"""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.modules.projects.models import Project


# === Lecturas básicas ===

def get_project_by_id(db: Session, project_id: UUID) -> Optional[Project]:
    """
    Obtiene un proyecto por su ID.
    """
    return (
        db.query(Project)
        .filter(Project.id == project_id)
        .first()
    )


def get_project_by_slug(db: Session, project_slug: str) -> Optional[Project]:
    """
    Obtiene un proyecto por su slug.
    El slug debe ser único globalmente.
    """
    return (
        db.query(Project)
        .filter(Project.project_slug == project_slug)
        .first()
    )


def list_projects_by_user(
    db: Session,
    auth_user_id: UUID,
    *,
    limit: int = 50,
    offset: int = 0,
) -> List[Project]:
    """
    Lista proyectos de un usuario, ordenados por creación descendente.

    BD 2.0 SSOT: auth_user_id (UUID) es el ownership canónico.

    Args:
        db: Sesión de base de datos.
        auth_user_id: UUID del usuario propietario (SSOT).
        limit: Máximo de resultados a devolver.
        offset: Desplazamiento para paginación.

    Returns:
        Lista de proyectos.
    """
    q = (
        db.query(Project)
        .filter(Project.auth_user_id == auth_user_id)
        .order_by(desc(Project.created_at))
        .offset(offset)
        .limit(limit)
    )
    return list(q.all())


# === Escrituras / persistencia ===

def save_project(db: Session, project: Project) -> Project:
    """
    Persiste un proyecto (insert o update) y devuelve la instancia actualizada.

    La lógica de negocio (slug único, validaciones, cambios de estado)
    se resuelve en la capa de servicios/facades.
    """
    db.add(project)
    db.flush()
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, project: Project) -> None:
    """
    Elimina (o marca para eliminar) un proyecto.

    La política de negocio (borrado lógico vs físico) debe manejarse
    en la capa de servicios. Este repositorio hace delete() directa.
    """
    db.delete(project)
    db.commit()


__all__ = [
    "get_project_by_id",
    "get_project_by_slug",
    "list_projects_by_user",
    "save_project",
    "delete_project",
]

# Fin del archivo backend/app/modules/projects/repositories/project_repository.py