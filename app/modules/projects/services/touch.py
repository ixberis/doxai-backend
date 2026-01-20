# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/services/touch.py

Servicio para actualizar `projects.updated_at` ("touch") cuando ocurren
cambios relevantes en el proyecto.

Casos de uso:
- Editar proyecto (nombre/descripción)
- Subir/eliminar/archivar archivos
- Cambios de fase RAG

Autor: DoxAI
Fecha: 2026-01-20
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.sql import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models import Project

_logger = logging.getLogger("projects.touch")


async def touch_project_updated_at(
    db: AsyncSession,
    project_id: UUID,
    *,
    reason: str = "unspecified",
) -> bool:
    """
    Actualiza `projects.updated_at` a NOW() (servidor DB) para marcar actividad reciente.
    
    Args:
        db: Sesión async de base de datos
        project_id: UUID del proyecto a actualizar
        reason: Descripción del motivo (para logging)
    
    Returns:
        True si se actualizó al menos un registro, False en caso contrario
        
    Note:
        Esta función solo hace flush(), el commit lo maneja el caller.
        Usa func.now() para que el timestamp venga del servidor DB.
    """
    try:
        stmt = (
            update(Project)
            .where(Project.id == project_id)
            .values(updated_at=func.now())
        )
        result = await db.execute(stmt)
        await db.flush()
        
        rowcount = result.rowcount
        
        if rowcount > 0:
            _logger.debug(
                "touch_project: project_id=%s reason=%s (server NOW())",
                str(project_id)[:8],
                reason,
            )
            return True
        else:
            _logger.warning(
                "touch_project: project_id=%s not found (rowcount=0) reason=%s",
                str(project_id)[:8],
                reason,
            )
            return False
            
    except Exception as e:
        _logger.error(
            "touch_project: project_id=%s reason=%s error=%s",
            str(project_id)[:8],
            reason,
            str(e),
            exc_info=True,
        )
        raise


__all__ = [
    "touch_project_updated_at",
]

# Fin del archivo backend/app/modules/projects/services/touch.py
