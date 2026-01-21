# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/queries/last_activity.py

Queries para calcular last_activity_at de proyectos.

SSOT: last_activity_at = GREATEST(projects.updated_at, MAX(project_file_event_logs.created_at))

Esta lógica usa una query directa (sin función SQL externa).

CRÍTICO:
- NO convertir UUIDs a strings
- NO fallback silencioso: re-raise excepciones

Autor: DoxAI
Fecha: 2026-01-21
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import text, bindparam
from sqlalchemy.ext.asyncio import AsyncSession

_logger = logging.getLogger("projects.last_activity")


async def get_last_activity_at_batch(
    db: AsyncSession,
    project_ids: List[UUID],
) -> Dict[UUID, Optional[datetime]]:
    """
    Obtiene last_activity_at para múltiples proyectos.
    
    SSOT: GREATEST(projects.updated_at, MAX(project_file_event_logs.created_at))
    
    Args:
        db: Sesión async de base de datos
        project_ids: Lista de UUIDs de proyectos (NO strings)
        
    Returns:
        Dict mapping project_id -> last_activity_at
        
    Raises:
        Exception: Re-raise cualquier error de DB (NO fallback silencioso)
    """
    if not project_ids:
        return {}
    
    try:
        # SSOT: Usar IN con bindparam(expanding=True) para lista de UUIDs
        # NO convertir a strings - pasar UUIDs directamente
        stmt = text("""
            SELECT 
                p.id AS project_id,
                GREATEST(
                    p.updated_at, 
                    COALESCE(
                        (SELECT MAX(e.created_at) 
                         FROM public.project_file_event_logs e 
                         WHERE e.project_id = p.id),
                        p.updated_at
                    )
                ) AS last_activity_at
            FROM public.projects p
            WHERE p.id IN :project_ids
        """).bindparams(bindparam("project_ids", expanding=True))
        
        # Pasar UUIDs directamente (NO strings)
        result = await db.execute(stmt, {"project_ids": project_ids})
        rows = result.mappings().fetchall()
        
        activity_map: Dict[UUID, Optional[datetime]] = {}
        for row in rows:
            pid = row["project_id"]
            # Normalizar a UUID si viene como otro tipo
            if not isinstance(pid, UUID):
                pid = UUID(str(pid))
            activity_map[pid] = row["last_activity_at"]
        
        _logger.debug(
            "last_activity_batch_ok: project_count=%d results=%d",
            len(project_ids),
            len(activity_map),
        )
        
        return activity_map
        
    except Exception as e:
        # CRÍTICO: NO fallback silencioso. Log ERROR y re-raise.
        _logger.error(
            "last_activity_batch_error: project_ids_count=%d error=%s",
            len(project_ids),
            str(e),
            exc_info=True,
        )
        raise


async def get_last_activity_at_single(
    db: AsyncSession,
    project_id: UUID,
) -> Optional[datetime]:
    """
    Obtiene last_activity_at para un solo proyecto.
    
    Args:
        db: Sesión async de base de datos
        project_id: UUID del proyecto
        
    Returns:
        Timestamp de última actividad o None si el proyecto no existe
    """
    result = await get_last_activity_at_batch(db, [project_id])
    return result.get(project_id)


async def get_latest_file_event_at(
    db: AsyncSession,
    project_id: UUID,
    *,
    strict: bool = True,
) -> Optional[datetime]:
    """
    Obtiene el timestamp del evento de archivo más reciente para un proyecto.
    
    Args:
        db: Sesión async de base de datos
        project_id: UUID del proyecto
        strict: Si es True (default), errores de DB se propagan; si es False, retorna None con warning
        
    Returns:
        Timestamp del último evento o None si no hay eventos
        
    Raises:
        Exception: Re-raise si strict=True (default) y ocurre error de DB
    """
    try:
        # SSOT: Cast explícito a uuid para evitar coerciones implícitas
        stmt = text("""
            SELECT MAX(created_at) AS latest_event
            FROM public.project_file_event_logs
            WHERE project_id = :project_id::uuid
        """)
        
        result = await db.execute(stmt, {"project_id": project_id})
        row = result.fetchone()
        
        return row[0] if row and row[0] else None
        
    except Exception as e:
        if strict:
            # SSOT: NO silenciar errores - log ERROR y re-raise
            _logger.error(
                "latest_file_event_error_strict: project_id=%s error=%s",
                str(project_id)[:8],
                str(e),
                exc_info=True,
            )
            raise
        else:
            # Legacy mode (deprecated) - solo warning
            _logger.warning(
                "latest_file_event_error_lenient: project_id=%s error=%s",
                str(project_id)[:8],
                str(e),
            )
            return None


__all__ = [
    "get_last_activity_at_batch",
    "get_last_activity_at_single", 
    "get_latest_file_event_at",
]

# Fin del archivo backend/app/modules/projects/facades/queries/last_activity.py
