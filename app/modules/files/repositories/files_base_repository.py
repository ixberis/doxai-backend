
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/repositories/files_base_repository.py

Repositorio async para la tabla base canónica `files_base`.

Responsabilidades:
- CRUD básico sobre FilesBase.
- Vinculación 1:1 con InputFile y ProductFile.
- Búsquedas por file_id, project_id y rol lógico.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files.enums.file_role_enum import FileRole
from app.modules.files.models.files_base_models import FilesBase


async def get_by_file_id(
    session: AsyncSession,
    file_id: UUID,
) -> Optional[FilesBase]:
    """
    Obtiene un registro FilesBase por su `file_id`.
    """
    stmt = select(FilesBase).where(FilesBase.file_id == file_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_by_project(
    session: AsyncSession,
    project_id: UUID,
    *,
    role: Optional[FileRole] = None,
) -> Sequence[FilesBase]:
    """
    Lista registros FilesBase de un proyecto, opcionalmente filtrando por rol.
    """
    stmt = select(FilesBase).where(FilesBase.project_id == project_id)

    if role is not None:
        stmt = stmt.where(FilesBase.file_role == role)

    result = await session.execute(stmt.order_by(FilesBase.created_at.desc()))
    return result.scalars().all()


async def create_for_input_file(
    session: AsyncSession,
    *,
    auth_user_id: UUID,
    project_id: UUID,
    input_file_id: UUID,
) -> FilesBase:
    """
    Crea un registro FilesBase asociado a un InputFile.

    NOTA:
    - No hace commit. Sólo agrega y hace flush. El commit se delega a la
      capa de servicio / fachada.
    """
    obj = FilesBase(
        auth_user_id=auth_user_id,
        project_id=project_id,
        file_role=FileRole.INPUT,
        input_file_id=input_file_id,
        product_file_id=None,
    )
    session.add(obj)
    await session.flush()
    return obj


async def create_for_product_file(
    session: AsyncSession,
    *,
    auth_user_id: UUID,
    project_id: UUID,
    product_file_id: UUID,
) -> FilesBase:
    """
    Crea un registro FilesBase asociado a un ProductFile.
    """
    obj = FilesBase(
        auth_user_id=auth_user_id,
        project_id=project_id,
        file_role=FileRole.PRODUCT,
        input_file_id=None,
        product_file_id=product_file_id,
    )
    session.add(obj)
    await session.flush()
    return obj


async def attach_input_file(
    session: AsyncSession,
    *,
    file_id: UUID,
    input_file_id: UUID,
) -> Optional[FilesBase]:
    """
    Adjunta un InputFile a un FilesBase existente (caso migración o relleno tardío).
    """
    obj = await get_by_file_id(session, file_id)
    if obj is None:
        return None

    obj.file_role = FileRole.INPUT
    obj.input_file_id = input_file_id
    obj.product_file_id = None
    await session.flush()
    return obj


async def attach_product_file(
    session: AsyncSession,
    *,
    file_id: UUID,
    product_file_id: UUID,
) -> Optional[FilesBase]:
    """
    Adjunta un ProductFile a un FilesBase existente.
    """
    obj = await get_by_file_id(session, file_id)
    if obj is None:
        return None

    obj.file_role = FileRole.PRODUCT
    obj.product_file_id = product_file_id
    obj.input_file_id = None
    await session.flush()
    return obj


__all__ = [
    "get_by_file_id",
    "list_by_project",
    "create_for_input_file",
    "create_for_product_file",
    "attach_input_file",
    "attach_product_file",
]

# Fin del archivo backend/app/modules/files/repositories/files_base_repository.py