
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/repositories/project_action_log_repository.py

Repositorio para la bitácora de acciones sobre proyectos (ProjectActionLog).

IMPORTANTE: Este repositorio es LEGACY y solo debe usarse para consultas.
Para registrar acciones, usar AuditLogger dentro de commit_or_raise.

Responsabilidades:
- Consultar acciones por proyecto (lectura)

NOTA: log_project_action está ELIMINADO - usar AuditLogger.log_action()
dentro de una transacción manejada por commit_or_raise.

Autor: Ixchel Beristáin
Fecha: 2025-11-21
Actualizado: 2026-01-16 (eliminado log_project_action, async queries)
"""

from __future__ import annotations

from typing import List
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models import ProjectActionLog


async def list_project_actions(
    db: AsyncSession,
    project_id: UUID,
    *,
    limit: int = 100,
    offset: int = 0,
) -> List[ProjectActionLog]:
    """
    Lista acciones de un proyecto, ordenadas de más reciente a más antigua.
    
    Args:
        db: AsyncSession SQLAlchemy
        project_id: ID del proyecto
        limit: Máximo de resultados (default 100)
        offset: Desplazamiento para paginación
        
    Returns:
        Lista de ProjectActionLog ordenados por created_at DESC
    """
    query = (
        select(ProjectActionLog)
        .where(ProjectActionLog.project_id == project_id)
        .order_by(desc(ProjectActionLog.created_at))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    return list(result.scalars().all())


__all__ = [
    "list_project_actions",
]

# Fin del archivo backend/app/modules/projects/repositories/project_action_log_repository.py
