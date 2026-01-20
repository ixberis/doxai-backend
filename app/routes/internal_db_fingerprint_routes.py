# -*- coding: utf-8 -*-
"""
backend/app/routes/internal_db_fingerprint_routes.py

Endpoint de diagnóstico para identificar a qué DB/Supabase está conectado el backend.

PATH: /_internal/db/fingerprint (y /api/_internal/db/fingerprint)
Método: GET
Protegido: Authorization: Bearer <APP_SERVICE_TOKEN> o X-Service-Token

Devuelve:
- current_database, current_schema, server_addr, server_port, pg_version
- current_user, session_user
- search_path
- counts de input_files, storage.objects
- buckets existentes
- storage.objects agrupados por bucket_id

Este endpoint es temporal/diagnóstico para investigar desconexiones entre
frontend/backend y la DB/Storage real.

Autor: DoxAI
Fecha: 2026-01-20
"""
from __future__ import annotations

import logging
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_async_session
from app.shared.internal_auth import InternalServiceAuth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/_internal/db", tags=["internal-db-diagnostics"])


class BucketInfo(BaseModel):
    """Info de un bucket."""
    id: str
    name: str
    public: bool
    created_at: Optional[str] = None


class StorageByBucket(BaseModel):
    """Conteo de objetos por bucket."""
    bucket_id: str
    count: int


class DbFingerprintResponse(BaseModel):
    """Respuesta completa del fingerprint."""
    # DB identity
    current_database: Optional[str] = None
    current_schema: Optional[str] = None
    server_addr: Optional[str] = None
    server_port: Optional[int] = None
    pg_version: Optional[str] = None
    
    # Session identity
    current_user: Optional[str] = None
    session_user: Optional[str] = None
    search_path: Optional[str] = None
    
    # Counts
    input_files_count: Optional[int] = None
    storage_objects_count: Optional[int] = None
    
    # Buckets
    buckets: list[BucketInfo] = []
    storage_by_bucket: list[StorageByBucket] = []
    
    # Errors (si alguna query falla)
    errors: list[str] = []


@router.get(
    "/fingerprint",
    response_model=DbFingerprintResponse,
    summary="DB fingerprint diagnóstico",
    description=(
        "Devuelve información de identidad de la DB y conteos de tablas clave. "
        "Requiere Authorization: Bearer <token> o X-Service-Token header."
    ),
)
async def db_fingerprint(
    _auth: InternalServiceAuth,
    session: AsyncSession = Depends(get_async_session),
) -> DbFingerprintResponse:
    """
    Endpoint de diagnóstico para identificar la DB conectada.
    
    Útil para verificar si el backend está conectado a la DB esperada
    (producción vs staging vs local).
    """
    response = DbFingerprintResponse()
    
    # 1. DB identity
    try:
        result = await session.execute(text("""
            SELECT 
                current_database() AS db,
                current_schema() AS schema,
                inet_server_addr()::text AS srv_addr,
                inet_server_port() AS srv_port,
                version() AS pg_version,
                current_user AS cur_user,
                session_user AS sess_user
        """))
        row = result.mappings().fetchone()
        if row:
            response.current_database = row.get("db")
            response.current_schema = row.get("schema")
            response.server_addr = row.get("srv_addr")
            response.server_port = row.get("srv_port")
            response.pg_version = row.get("pg_version")
            response.current_user = row.get("cur_user")
            response.session_user = row.get("sess_user")
    except Exception as e:
        response.errors.append(f"db_identity: {type(e).__name__}: {str(e)[:100]}")
    
    # 2. Search path
    try:
        result = await session.execute(text("SHOW search_path"))
        row = result.fetchone()
        if row:
            response.search_path = row[0]
    except Exception as e:
        response.errors.append(f"search_path: {type(e).__name__}")
    
    # 3. Count input_files
    try:
        result = await session.execute(text("SELECT count(*) FROM public.input_files"))
        row = result.fetchone()
        if row:
            response.input_files_count = row[0]
    except Exception as e:
        response.errors.append(f"input_files_count: {type(e).__name__}: {str(e)[:100]}")
    
    # 4. Count storage.objects
    try:
        result = await session.execute(text("SELECT count(*) FROM storage.objects"))
        row = result.fetchone()
        if row:
            response.storage_objects_count = row[0]
    except Exception as e:
        response.errors.append(f"storage_objects_count: {type(e).__name__}: {str(e)[:100]}")
    
    # 5. List buckets
    try:
        result = await session.execute(text("""
            SELECT id, name, public, created_at::text
            FROM storage.buckets
            ORDER BY created_at DESC
            LIMIT 20
        """))
        for row in result.mappings():
            response.buckets.append(BucketInfo(
                id=row["id"],
                name=row["name"],
                public=row["public"],
                created_at=row.get("created_at"),
            ))
    except Exception as e:
        response.errors.append(f"buckets: {type(e).__name__}: {str(e)[:100]}")
    
    # 6. Storage objects grouped by bucket
    try:
        result = await session.execute(text("""
            SELECT bucket_id, count(*) AS cnt
            FROM storage.objects
            GROUP BY bucket_id
            ORDER BY cnt DESC
        """))
        for row in result.mappings():
            response.storage_by_bucket.append(StorageByBucket(
                bucket_id=row["bucket_id"],
                count=row["cnt"],
            ))
    except Exception as e:
        response.errors.append(f"storage_by_bucket: {type(e).__name__}: {str(e)[:100]}")
    
    logger.info(
        "db_fingerprint: db=%s server=%s:%s input_files=%s storage_objects=%s buckets=%d",
        response.current_database,
        response.server_addr,
        response.server_port,
        response.input_files_count,
        response.storage_objects_count,
        len(response.buckets),
    )
    
    return response
