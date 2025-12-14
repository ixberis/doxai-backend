
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/files_search_service.py

Servicios de búsqueda de archivos de proyecto en el módulo Files (Files v2).

Responsabilidades:
- Buscar archivos INSUMO y PRODUCTO de un proyecto.
- Unificar resultados en una vista lógica tipo `ProjectFileUnionResponse`.
- Ofrecer filtros básicos por rol y texto libre.

Decisiones Files v2:
- Async only (AsyncSession).
- Usa directamente los modelos InputFile y ProductFile para eficiencia.
- Los resultados se devuelven como ProjectFileUnionResponse (schema Pydantic).

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from typing import List, Optional
from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files.enums import FileCategory, FileLanguage, ProductVersion
from app.modules.files.models.input_file_models import InputFile
from app.modules.files.models.product_file_models import ProductFile
from app.modules.files.schemas.product_file_schemas import ProjectFileUnionResponse


class FilesSearchService:
    """
    Servicio de búsqueda de archivos para Files v2.
    
    Responsabilidades:
    - Buscar archivos INSUMO y PRODUCTO de un proyecto.
    - Unificar resultados con filtros básicos.
    - Ofrecer paginación y ordenamiento.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def search(
        self,
        *,
        project_id: UUID | int,
        category: Optional[FileCategory] = None,
        language: Optional[FileLanguage] = None,
        version: Optional[ProductVersion] = None,
        order_by: Optional[str] = None,
        descending: bool = False,
        limit: int = 100,
        offset: int = 0,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> List[InputFile | ProductFile]:
        """
        Busca archivos de un proyecto con filtros opcionales.
        
        Parámetros
        ----------
        project_id : UUID | int
            ID del proyecto
        category : Optional[FileCategory]
            Filtrar por categoría (input o product_files)
        language : Optional[FileLanguage]
            Filtrar por idioma (solo para InputFiles)
        version : Optional[ProductVersion]
            Filtrar por versión (solo para ProductFiles)
        order_by : Optional[str]
            Campo para ordenar (created_at, size_bytes)
        descending : bool
            Orden descendente si True
        limit : int
            Máximo de resultados
        offset : int
            Offset para paginación
        date_from : Optional[datetime]
            Fecha inicio del rango
        date_to : Optional[datetime]
            Fecha fin del rango
            
        Retorna
        -------
        List[InputFile | ProductFile]
            Lista de archivos que cumplen los criterios
            
        Raises
        ------
        ValueError
            Si order_by contiene un campo no permitido
        """
        # Validar order_by para seguridad
        allowed_order_fields = {"created_at", "size_bytes"}
        if order_by and order_by not in allowed_order_fields:
            raise ValueError(f"Order by field '{order_by}' not allowed")
        
        results: List[InputFile | ProductFile] = []
        safe_limit = max(1, min(1000, int(limit)))
        safe_offset = max(0, int(offset))
        
        # Buscar InputFiles si no se filtra solo por productos
        if category is None or category == FileCategory.input:
            stmt_inputs = select(InputFile).where(InputFile.project_id == project_id)
            
            if language:
                stmt_inputs = stmt_inputs.where(InputFile.input_file_language == language)
            
            if date_from:
                stmt_inputs = stmt_inputs.where(InputFile.input_file_uploaded_at >= date_from)
            if date_to:
                stmt_inputs = stmt_inputs.where(InputFile.input_file_uploaded_at <= date_to)
            
            # Ordenamiento
            if order_by == "created_at":
                order_col = InputFile.input_file_uploaded_at.desc() if descending else InputFile.input_file_uploaded_at
            elif order_by == "size_bytes":
                order_col = InputFile.input_file_size_bytes.desc() if descending else InputFile.input_file_size_bytes
            else:
                order_col = InputFile.input_file_uploaded_at.desc()
            
            stmt_inputs = stmt_inputs.order_by(order_col).limit(safe_limit).offset(safe_offset)
            res_inputs = await self.db.execute(stmt_inputs)
            results.extend(res_inputs.scalars().all())
        
        # Buscar ProductFiles si no se filtra solo por inputs
        if category is None or category == FileCategory.product_files:
            stmt_products = select(ProductFile).where(ProductFile.project_id == project_id)
            
            if version:
                stmt_products = stmt_products.where(ProductFile.product_file_version == version)
            
            if date_from:
                stmt_products = stmt_products.where(ProductFile.product_file_generated_at >= date_from)
            if date_to:
                stmt_products = stmt_products.where(ProductFile.product_file_generated_at <= date_to)
            
            # Ordenamiento
            if order_by == "created_at":
                order_col = ProductFile.product_file_generated_at.desc() if descending else ProductFile.product_file_generated_at
            elif order_by == "size_bytes":
                order_col = ProductFile.product_file_size_bytes.desc() if descending else ProductFile.product_file_size_bytes
            else:
                order_col = ProductFile.product_file_generated_at.desc()
            
            stmt_products = stmt_products.order_by(order_col).limit(safe_limit).offset(safe_offset)
            res_products = await self.db.execute(stmt_products)
            results.extend(res_products.scalars().all())
        
        return results


async def search_project_files(
    session: AsyncSession,
    *,
    project_id: UUID,
    query_text: Optional[str] = None,
    include_inputs: bool = True,
    include_products: bool = True,
    limit: int = 100,
) -> List[ProjectFileUnionResponse]:
    """
    Busca archivos de un proyecto (insumos y productos) y devuelve una lista
    unificada de ProjectFileUnionResponse.

    Parámetros
    ----------
    project_id:
        Proyecto sobre el que se realiza la búsqueda.
    query_text:
        Texto libre a buscar en nombre original o de despliegue.
        Si es None o cadena vacía, no se filtra por texto.
    include_inputs / include_products:
        Flags para limitar la búsqueda a insumos, productos o ambos.
    limit:
        Máximo de resultados a devolver (suma de insumos + productos).

    Retorna
    -------
    list[ProjectFileUnionResponse]
        Lista de resultados ordenados por fecha (más recientes primero),
        combinando insumos y productos.
    """
    results: list[ProjectFileUnionResponse] = []
    safe_limit = max(1, min(1000, int(limit)))

    like_pattern = f"%{query_text}%" if query_text else None

    # ------------------------------------------------------------------
    # 1) Buscar INSUMOS
    # ------------------------------------------------------------------
    if include_inputs:
        stmt_inputs = select(InputFile).where(InputFile.project_id == project_id)

        if like_pattern:
            stmt_inputs = stmt_inputs.where(
                or_(
                    InputFile.input_file_original_name.ilike(like_pattern),
                    InputFile.input_file_display_name.ilike(like_pattern),
                )
            )

        stmt_inputs = stmt_inputs.order_by(InputFile.input_file_uploaded_at.desc()).limit(
            safe_limit
        )
        res_inputs = await session.execute(stmt_inputs)
        input_files = list(res_inputs.scalars().all())

        for inp in input_files:
            results.append(
                ProjectFileUnionResponse(
                    file_id=inp.file_id or inp.input_file_id,
                    project_id=inp.project_id,
                    role="input",
                    category=FileCategory.input,
                    original_name=inp.input_file_original_name,
                    display_name=inp.input_file_display_name,
                    mime_type=inp.input_file_mime_type,
                    size_bytes=inp.input_file_size_bytes,
                    created_at=inp.input_file_uploaded_at,
                )
            )

    # ------------------------------------------------------------------
    # 2) Buscar PRODUCTOS
    # ------------------------------------------------------------------
    if include_products:
        stmt_products = select(ProductFile).where(ProductFile.project_id == project_id)

        if like_pattern:
            stmt_products = stmt_products.where(
                or_(
                    ProductFile.product_file_original_name.ilike(like_pattern),
                    ProductFile.product_file_display_name.ilike(like_pattern),
                )
            )

        stmt_products = stmt_products.order_by(
            ProductFile.product_file_generated_at.desc()
        ).limit(safe_limit)
        res_products = await session.execute(stmt_products)
        product_files = list(res_products.scalars().all())

        for pf in product_files:
            results.append(
                ProjectFileUnionResponse(
                    file_id=pf.file_id or pf.product_file_id,
                    project_id=pf.project_id,
                    role="product",
                    category=None,  # para productos la categoría no es estrictamente necesaria aquí
                    original_name=pf.product_file_original_name,
                    display_name=pf.product_file_display_name,
                    mime_type=pf.product_file_mime_type,
                    size_bytes=pf.product_file_size_bytes,
                    created_at=pf.product_file_generated_at,
                )
            )

    # ------------------------------------------------------------------
    # 3) Ordenar y truncar resultados combinados
    # ------------------------------------------------------------------
    results.sort(key=lambda item: item.created_at, reverse=True)
    return results[:safe_limit]


__all__ = ["FilesSearchService", "search_project_files"]

# Fin del archivo backend/app/modules/files/services/files_search_service.py