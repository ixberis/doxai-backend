# -*- coding: utf-8 -*-
"""
backend/app/routes/internal_files_recent_routes.py

Endpoint de diagnóstico para listar los archivos insumo más recientes.

PATH: /_internal/files/input-files/recent (y /api/_internal/files/input-files/recent)
Método: GET
Protegido: InternalServiceAuth (Authorization: Bearer <APP_SERVICE_TOKEN> o X-Service-Token)

Query Params:
- project_id: UUID (opcional) - filtrar por proyecto
- auth_user_id: UUID (opcional) - filtrar por usuario
- limit: int (default 20, max 100)

Devuelve:
- Lista de input_files con campos mínimos para diagnóstico

Este endpoint es temporal/diagnóstico para investigar si los registros
se están guardando correctamente.

Autor: DoxAI
Fecha: 2026-01-20
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_async_session
from app.shared.internal_auth import InternalServiceAuth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/_internal/files", tags=["internal-files-diagnostics"])


class RecentInputFileItem(BaseModel):
    """Item de archivo reciente para diagnóstico."""
    input_file_id: str
    project_id: str
    auth_user_id: str
    storage_key: str
    original_name: str
    mime_type: str
    size_bytes: int
    status: Optional[str] = None
    is_active: bool = True
    is_archived: bool = False
    uploaded_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class RecentInputFilesResponse(BaseModel):
    """Respuesta del listado de archivos recientes."""
    success: bool
    count: int
    items: List[RecentInputFileItem]
    filters_applied: dict
    error: Optional[str] = None


@router.get(
    "/input-files/recent",
    response_model=RecentInputFilesResponse,
    summary="Listar input_files recientes",
    description=(
        "Lista los archivos insumo más recientes con filtros opcionales. "
        "Requiere Authorization: Bearer <token> o X-Service-Token header."
    ),
)
async def list_recent_input_files(
    _auth: InternalServiceAuth,
    session: AsyncSession = Depends(get_async_session),
    project_id: Optional[UUID] = Query(None, description="Filtrar por project_id"),
    auth_user_id: Optional[UUID] = Query(None, description="Filtrar por auth_user_id"),
    limit: int = Query(20, ge=1, le=100, description="Máximo de resultados"),
) -> RecentInputFilesResponse:
    """
    Endpoint de diagnóstico para listar archivos recientes.
    
    Permite verificar inmediatamente si un upload quedó registrado en la DB.
    """
    filters_applied = {
        "project_id": str(project_id) if project_id else None,
        "auth_user_id": str(auth_user_id) if auth_user_id else None,
        "limit": limit,
    }
    
    try:
        # Build dynamic WHERE clause
        conditions = []
        params = {"limit": limit}
        
        if project_id:
            conditions.append("project_id = :project_id")
            params["project_id"] = str(project_id)
        
        if auth_user_id:
            conditions.append("auth_user_id = :auth_user_id")
            params["auth_user_id"] = str(auth_user_id)
        
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        query = text(f"""
            SELECT 
                input_file_id::text,
                project_id::text,
                auth_user_id::text,
                input_file_storage_path AS storage_key,
                input_file_original_name AS original_name,
                input_file_mime_type AS mime_type,
                input_file_size_bytes AS size_bytes,
                input_file_status::text AS status,
                input_file_is_active AS is_active,
                input_file_is_archived AS is_archived,
                input_file_uploaded_at AS uploaded_at,
                created_at
            FROM public.input_files
            {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit
        """)
        
        result = await session.execute(query, params)
        rows = result.mappings().fetchall()
        
        items = [
            RecentInputFileItem(
                input_file_id=row["input_file_id"],
                project_id=row["project_id"],
                auth_user_id=row["auth_user_id"],
                storage_key=row["storage_key"],
                original_name=row["original_name"],
                mime_type=row["mime_type"],
                size_bytes=row["size_bytes"],
                status=row["status"],
                is_active=row["is_active"],
                is_archived=row["is_archived"],
                uploaded_at=row["uploaded_at"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
        
        logger.info(
            "internal_files_recent: count=%d project=%s user=%s",
            len(items),
            str(project_id)[:8] if project_id else "all",
            str(auth_user_id)[:8] if auth_user_id else "all",
        )
        
        return RecentInputFilesResponse(
            success=True,
            count=len(items),
            items=items,
            filters_applied=filters_applied,
        )
        
    except Exception as e:
        logger.error("internal_files_recent: error=%s", e, exc_info=True)
        return RecentInputFilesResponse(
            success=False,
            count=0,
            items=[],
            filters_applied=filters_applied,
            error=f"{type(e).__name__}: {str(e)[:200]}",
        )
