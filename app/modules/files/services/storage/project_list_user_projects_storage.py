
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/storage/project_list_user_projects_storage.py

Devuelve la lista de proyectos de un usuario (activos/cerrados) desde la BD.
No accede a Storage.

Autor: DoxAI
Actualizado: 2025-11-01
"""

from __future__ import annotations

from typing import Dict, List
from sqlalchemy.orm import Session
from app.modules.projects.models.project_models import Project


def list_user_projects_from_db(user_id: str, db: Session) -> Dict[str, List[dict]]:
    if not user_id:
        return {"proyectos_en_proceso": [], "proyectos_cerrados": []}

    items = db.query(Project).filter(Project.user_id == user_id).all()
    en, ce = [], []
    for p in items:
        dto = {
            "project_id": str(p.project_id),
            "project_name": p.project_name,
            "project_description": p.project_description,
            "project_slug": p.project_slug,
            "project_created_at": p.project_created_at,
            "project_updated_at": p.project_updated_at,
            "project_archive_at": p.project_archived_at,
        }
        (ce if p.project_is_closed else en).append(dto)

    return {"proyectos_en_proceso": en, "proyectos_cerrados": ce}
# Fin del archivo backend\app\modules\files\services\storage\project_list_user_projects_storage.py








