
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/input_file_lookup_service.py

Servicios para búsqueda específica de archivos INSUMO.

Responsabilidades:
- Resolver InputFile a partir de un file_id canónico (files_base).
- Buscar InputFile por ruta de storage dentro de un proyecto.

Decisiones Files v2:
- Async only (AsyncSession).
- Usa FilesBase + InputFile para búsquedas por file_id.
- Para búsquedas por storage_path filtra directamente sobre InputFile.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files.models.files_base_models import FilesBase
from app.modules.files.models.input_file_models import InputFile


async def get_input_file_by_file_id(
    session: AsyncSession,
    *,
    file_id: UUID,
) -> Optional[InputFile]:
    """
    Devuelve el InputFile asociado a un file_id canónico, si existe.

    Estrategia de búsqueda (robusta):
    1. Busca directamente en input_files.file_id (FK)
    2. Fallback: JOIN con files_base para casos legacy
    
    Esto permite que funcione aunque files_base no tenga el registro.
    """
    # 1) Búsqueda directa en input_files.file_id
    stmt_direct = select(InputFile).where(InputFile.file_id == file_id)
    result = await session.execute(stmt_direct)
    input_file = result.scalar_one_or_none()
    
    if input_file is not None:
        return input_file
    
    # 2) Fallback: JOIN con files_base (para casos legacy)
    stmt_join = (
        select(InputFile)
        .join(FilesBase, FilesBase.input_file_id == InputFile.input_file_id)
        .where(FilesBase.file_id == file_id)
    )
    result = await session.execute(stmt_join)
    return result.scalar_one_or_none()


async def get_input_file_by_storage_path(
    session: AsyncSession,
    *,
    project_id: UUID,
    storage_path: str,
) -> Optional[InputFile]:
    """
    Busca un InputFile por `project_id` y `storage_path`.
    """
    stmt = select(InputFile).where(
        and_(
            InputFile.project_id == project_id,
            InputFile.input_file_storage_path == storage_path,
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


__all__ = [
    "get_input_file_by_file_id",
    "get_input_file_by_storage_path",
]

# Fin del archivo backend/app/modules/files/services/input_file_lookup_service.py






