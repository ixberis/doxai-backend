
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/facades/product_files/query.py

Fachada funcional para consultar archivos PRODUCTO.

Responsabilidades:
- Obtener detalle de un archivo producto por ID.
- Listar archivos producto activos de un proyecto con filtros básicos.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from typing import Optional, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files.enums import ProductFileType
from app.modules.files.facades.errors import FileNotFoundError
from app.modules.files.schemas import ProductFileResponse
from app.modules.files.services import (
    get_product_file,
    list_active_product_files,
)


async def get_product_file_details(
    db: AsyncSession,
    *,
    product_file_id: UUID,
    include_inactive: bool = False,
) -> ProductFileResponse:
    """
    Devuelve un ProductFileResponse a partir de su ID.

    Args:
        product_file_id: ID del archivo producto.
        include_inactive: Si True, incluye archivos invalidados/inactivos.
                          Útil para operaciones idempotentes como DELETE.

    Lanza FileNotFoundError si no existe (o si está inactivo y include_inactive=False).
    """
    obj = await get_product_file(
        session=db,
        product_file_id=product_file_id,
    )
    if obj is None:
        raise FileNotFoundError("No se encontró el archivo producto solicitado")
    
    # Si no incluye inactivos y está inactivo, lanzar 404
    if not include_inactive and not obj.product_file_is_active:
        raise FileNotFoundError("No se encontró el archivo producto solicitado")

    return ProductFileResponse.model_validate(obj)


async def list_project_product_files(
    db: AsyncSession,
    *,
    project_id: UUID,
    file_type: Optional[ProductFileType] = None,
    sort_by: str = "display_name",
    sort_order: str = "asc",
    limit: int = 50,
    offset: int = 0,
) -> List[ProductFileResponse]:
    """
    Lista archivos producto activos de un proyecto, con filtros básicos.
    """
    items = await list_active_product_files(
        session=db,
        project_id=project_id,
        file_type=file_type,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )
    return [ProductFileResponse.model_validate(pf) for pf in items]


__all__ = ["get_product_file_details", "list_project_product_files"]

# Fin del archivo backend/app/modules/files/facades/product_files/query.py