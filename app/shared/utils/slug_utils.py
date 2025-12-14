
# -*- coding: utf-8 -*-
"""
backend/app/utils/slug_generator.py

Utilidad para generar slugs únicos para proyectos en DoxAI.

Autor: Ixchel Beristain
Fecha: 09/06/2025
"""

import re
import unicodedata
from sqlalchemy.orm import Session



def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", value)


def generate_unique_slug(db: Session, project_name: str) -> str:
    from app.modules.projects.models.project_models import Project
    base_slug = slugify(project_name)
    slug = base_slug
    index = 1
    while db.query(Project).filter(Project.project_slug == slug).first():
        slug = f"{base_slug}-{index}"
        index += 1
    return slug







