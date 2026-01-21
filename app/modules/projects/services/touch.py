# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/services/touch.py

Servicio para actualizar `projects.updated_at` ("touch") cuando ocurren
cambios relevantes en el proyecto.

Casos de uso:
- Editar proyecto (nombre/descripción)
- Subir/eliminar/archivar archivos
- Cambios de fase RAG

SSOT:
- Usa UPDATE ... SET updated_at = timezone('utc', now()) RETURNING updated_at
- El timestamp viene del servidor de DB (no del reloj del app)
- Transaction-agnostic: no hace flush() ni commit(), el caller maneja la transacción
- Logging con txid_current() para correlación transaccional

Autor: DoxAI
Fecha: 2026-01-21
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
        True si se actualizó al menos un registro, False si el proyecto no existe
        
    Note:
        Transaction-agnostic: NO hace flush() ni commit().
        El UPDATE con RETURNING ya sincroniza los cambios en la transacción actual.
        El caller es responsable de commit() o rollback().
        
        Incluye logging con txid_current() para correlación transaccional.
    """
    try:
        # Obtener txid_current() y updated_at ANTES para logging de correlación
        before_result = await db.execute(
            text("""
                SELECT 
                    txid_current() AS txid,
                    updated_at 
                FROM public.projects 
                WHERE id = :id
            """),
            {"id": str(project_id)},
        )
        before_row = before_result.mappings().fetchone()
        
        if before_row is None:
            # El proyecto no existe
            _logger.warning(
                "touch_project_before_not_found: project_id=%s reason=%s (project does not exist)",
                str(project_id)[:8],
                reason,
            )
            return False
        
        txid = before_row.get("txid")
        updated_at_before = before_row.get("updated_at")
        
        _logger.info(
            "touch_project_before: project_id=%s txid=%s updated_at_before=%s reason=%s",
            str(project_id)[:8],
            txid,
            updated_at_before,
            reason,
        )
        
        # Ejecutar UPDATE con RETURNING para obtener el nuevo valor
        # El RETURNING asegura que el cambio está sincronizado en la transacción
        stmt = text("""
            UPDATE public.projects 
            SET updated_at = timezone('utc', now())
            WHERE id = :id
            RETURNING updated_at
        """)
        result = await db.execute(stmt, {"id": str(project_id)})
        row = result.fetchone()
        
        # NO flush() aquí - el UPDATE con RETURNING ya sincroniza
        # El caller hace commit() al final de la transacción
        
        if row is not None:
            updated_at_after = row[0]
            _logger.info(
                "touch_project_after: project_id=%s txid=%s updated_at_after=%s rowcount=1 reason=%s",
                str(project_id)[:8],
                txid,
                updated_at_after,
                reason,
            )
            return True
        else:
            # Esto no debería ocurrir si before_row existía, pero por seguridad
            _logger.error(
                "touch_project_update_no_rows: project_id=%s txid=%s reason=%s (unexpected: project existed before but UPDATE returned no rows)",
                str(project_id)[:8],
                txid,
                reason,
            )
            return False
            
    except Exception as e:
        _logger.error(
            "touch_project_error: project_id=%s reason=%s error=%s",
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
