# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/project_files_query.py

Servicio para consultas unificadas de archivos de proyecto (input + product).
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, union_all, literal
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files.enums import FileCategory
from app.modules.files.models.input_file_models import InputFile
from app.modules.files.models.product_file_models import ProductFile


class ProjectFilesQueryService:
    """Servicio para consultas unificadas de archivos de proyecto."""

    ALLOWED_ORDER_BY = {"created_at", "size_bytes", "file_name"}

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_project_files(
        self,
        project_id: UUID,
        category: Optional[FileCategory] = None,
        search: Optional[str] = None,
        include_archived: bool = False,
        order_by: str = "created_at",
        descending: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> List[dict]:
        """
        Lista todos los archivos de un proyecto (input + product).
        
        Args:
            project_id: ID del proyecto
            category: Filtro opcional por categoría
            search: Búsqueda en nombre o ruta
            include_archived: Incluir archivados
            order_by: Campo de ordenamiento
            descending: Orden descendente
            limit: Límite de resultados
            offset: Offset de paginación
            
        Returns:
            Lista de diccionarios con información de archivos
        """
        if order_by not in self.ALLOWED_ORDER_BY:
            raise ValueError(f"Invalid order_by field: {order_by}")

        # Construir query unificada
        queries = []

        # Input files
        if category is None or category == FileCategory.input:
            input_query = select(
                InputFile.input_file_id.label("id"),
                InputFile.project_id,
                literal(FileCategory.input.value).label("category"),
                InputFile.input_file_display_name.label("file_name"),
                InputFile.input_file_storage_path.label("storage_path"),
                InputFile.input_file_size_bytes.label("size_bytes"),
                InputFile.input_file_uploaded_at.label("created_at"),
            ).where(
                InputFile.project_id == project_id,
                InputFile.input_file_is_active == True,
            )

            if not include_archived:
                input_query = input_query.where(InputFile.input_file_is_archived == False)

            if search:
                search_pattern = f"%{search}%"
                input_query = input_query.where(
                    InputFile.input_file_display_name.ilike(search_pattern)
                    | InputFile.input_file_storage_path.ilike(search_pattern)
                )

            queries.append(input_query)

        # Product files
        if category is None or category == FileCategory.product_files:
            product_query = select(
                ProductFile.product_file_id.label("id"),
                ProductFile.project_id,
                literal(FileCategory.product_files.value).label("category"),
                ProductFile.product_file_display_name.label("file_name"),
                ProductFile.product_file_storage_path.label("storage_path"),
                ProductFile.product_file_size_bytes.label("size_bytes"),
                ProductFile.product_file_generated_at.label("created_at"),
            ).where(
                ProductFile.project_id == project_id,
                ProductFile.product_file_is_active == True,
            )

            if not include_archived:
                product_query = product_query.where(ProductFile.product_file_is_archived == False)

            if search:
                search_pattern = f"%{search}%"
                product_query = product_query.where(
                    ProductFile.product_file_display_name.ilike(search_pattern)
                    | ProductFile.product_file_storage_path.ilike(search_pattern)
                )

            queries.append(product_query)

        if not queries:
            return []

        # Union - siempre crear subquery explícito para ordenamiento consistente
        if len(queries) == 1:
            union_subquery = queries[0].subquery()
        else:
            union_subquery = union_all(*queries).subquery()

        stmt = select(union_subquery)

        # Ordenamiento y paginación usando el subquery
        if order_by == "created_at":
            stmt = stmt.order_by(union_subquery.c.created_at.desc() if descending else union_subquery.c.created_at.asc())
        elif order_by == "size_bytes":
            stmt = stmt.order_by(union_subquery.c.size_bytes.desc() if descending else union_subquery.c.size_bytes.asc())
        elif order_by == "file_name":
            stmt = stmt.order_by(union_subquery.c.file_name.desc() if descending else union_subquery.c.file_name.asc())

        stmt = stmt.limit(limit).offset(offset)

        # Ejecutar
        result = await self.db.execute(stmt)
        rows = result.all()

        return [
            {
                "id": row.id,
                "project_id": row.project_id,
                "category": FileCategory(row.category),
                "file_name": row.file_name,
                "storage_path": row.storage_path,
                "size_bytes": row.size_bytes,
                "created_at": row.created_at,
            }
            for row in rows
        ]


__all__ = ["ProjectFilesQueryService"]
