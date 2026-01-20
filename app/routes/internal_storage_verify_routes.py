# -*- coding: utf-8 -*-
"""
backend/app/routes/internal_storage_verify_routes.py

Endpoint de diagnóstico para verificar que el backend puede hacer roundtrip
al bucket users-files usando las mismas credenciales que el upload real.

PATH: /_internal/storage/verify-users-files (y /api/_internal/storage/verify-users-files)
Método: POST
Protegido: InternalServiceAuth (Authorization: Bearer <APP_SERVICE_TOKEN> o X-Service-Token)

Flujo:
1. Sube un archivo pequeño healthcheck.txt a key healthcheck/<uuid>.txt
2. Lista objetos con prefijo healthcheck/ y verifica que el objeto existe
3. Verifica en storage.objects de la DB que el objeto existe
4. Borra el objeto
5. Devuelve resultado del roundtrip

Este endpoint es temporal/diagnóstico para investigar si el storage
está funcionando correctamente.

Autor: DoxAI
Fecha: 2026-01-20
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.config import settings
from app.shared.database.database import get_async_session
from app.shared.internal_auth import InternalServiceAuth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/_internal/storage", tags=["internal-storage-diagnostics"])


class StorageVerifyResponse(BaseModel):
    """Respuesta del verify de storage."""
    success: bool
    
    # Config (redacted)
    supabase_url_redacted: Optional[str] = None
    bucket_name: str
    has_service_role_key: bool
    
    # Roundtrip results
    upload_success: bool = False
    upload_ms: Optional[float] = None
    object_key: Optional[str] = None
    
    list_success: bool = False
    list_ms: Optional[float] = None
    object_found: bool = False
    object_size: Optional[int] = None
    object_created_at: Optional[str] = None
    
    # DB verification of storage.objects
    db_check_success: bool = False
    db_check_ms: Optional[float] = None
    db_object_exists: bool = False
    db_object_count: int = 0
    
    delete_success: bool = False
    delete_ms: Optional[float] = None
    
    # Errors
    error_phase: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


def _redact_url(url: str) -> str:
    """Redacta una URL para no exponer el proyecto completo."""
    if not url:
        return "<not-set>"
    # Mostrar solo dominio/host
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc[:30]}..."
    except Exception:
        return "<parse-error>"


@router.post(
    "/verify-users-files",
    response_model=StorageVerifyResponse,
    summary="Verify storage roundtrip",
    description=(
        "Hace un roundtrip completo al bucket users-files: upload, list, DB check, delete. "
        "Requiere Authorization: Bearer <token> o X-Service-Token header."
    ),
)
async def verify_storage_users_files(
    _auth: InternalServiceAuth,
    session: AsyncSession = Depends(get_async_session),
) -> StorageVerifyResponse:
    """
    Endpoint de diagnóstico para verificar storage.
    
    Usa exactamente el mismo cliente/credenciales que el upload real.
    Ahora incluye verificación en storage.objects de la DB.
    """
    from app.shared.utils.http_storage_client import SupabaseStorageHTTPClient
    
    bucket_name = settings.supabase_bucket_name or "users-files"
    supabase_url = str(settings.supabase_url) if settings.supabase_url else None
    has_key = bool(settings.supabase_service_role_key)
    
    response = StorageVerifyResponse(
        success=False,
        supabase_url_redacted=_redact_url(supabase_url) if supabase_url else "<not-set>",
        bucket_name=bucket_name,
        has_service_role_key=has_key,
    )
    
    if not supabase_url or not has_key:
        response.error_phase = "config"
        response.error_code = "MISSING_CONFIG"
        response.error_message = "SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not configured"
        logger.error("storage_verify: missing config")
        return response
    
    # Crear cliente
    try:
        client = SupabaseStorageHTTPClient()
    except Exception as e:
        response.error_phase = "client_init"
        response.error_code = type(e).__name__
        response.error_message = str(e)[:200]
        logger.error("storage_verify: client init failed: %s", e)
        return response
    
    # Generate unique key for healthcheck
    test_id = str(uuid4())
    object_key = f"healthcheck/{test_id}.txt"
    test_content = f"healthcheck {datetime.now(timezone.utc).isoformat()}".encode()
    response.object_key = object_key
    
    # Phase 1: Upload
    try:
        start = time.perf_counter()
        await client.upload_file(
            bucket=bucket_name,
            path=object_key,
            file_data=test_content,
            content_type="text/plain",
            overwrite=True,
        )
        response.upload_ms = round((time.perf_counter() - start) * 1000, 2)
        response.upload_success = True
        logger.info("storage_verify: upload success key=%s ms=%.2f", object_key, response.upload_ms)
    except Exception as e:
        response.error_phase = "upload"
        response.error_code = type(e).__name__
        response.error_message = str(e)[:200]
        logger.error("storage_verify: upload failed: %s", e)
        return response
    
    # Phase 2: List to verify (API side)
    try:
        start = time.perf_counter()
        files = await client.list_files(
            bucket=bucket_name,
            prefix="healthcheck/",
            limit=100,
        )
        response.list_ms = round((time.perf_counter() - start) * 1000, 2)
        response.list_success = True
        
        # Find our object - support both "healthcheck/{uuid}.txt" and "{uuid}.txt"
        target_name = f"{test_id}.txt"
        full_target = f"healthcheck/{test_id}.txt"
        
        file_list = files if isinstance(files, list) else files.get("files", [])
        for f in file_list:
            fname = f.get("name", "")
            # Match by exact name, suffix, or full path
            if fname == target_name or fname == full_target or fname.endswith(f"/{target_name}") or fname.endswith(target_name):
                response.object_found = True
                response.object_size = f.get("metadata", {}).get("size") or f.get("size")
                response.object_created_at = f.get("created_at")
                break
        
        logger.info(
            "storage_verify: list success found=%s ms=%.2f files_count=%d",
            response.object_found,
            response.list_ms,
            len(file_list),
        )
    except Exception as e:
        response.error_phase = "list"
        response.error_code = type(e).__name__
        response.error_message = str(e)[:200]
        logger.error("storage_verify: list failed: %s", e, exc_info=True)
        # Continue to try DB check and delete anyway
    
    # Phase 2.5: Verify in storage.objects table (DB side)
    try:
        start = time.perf_counter()
        result = await session.execute(
            text("""
                SELECT count(*) AS cnt
                FROM storage.objects
                WHERE bucket_id = :bucket AND name = :object_key
            """),
            {"bucket": bucket_name, "object_key": object_key},
        )
        row = result.fetchone()
        response.db_check_ms = round((time.perf_counter() - start) * 1000, 2)
        response.db_check_success = True
        
        if row:
            response.db_object_count = row[0]
            response.db_object_exists = row[0] > 0
        
        logger.info(
            "storage_verify: db_check success exists=%s count=%d ms=%.2f",
            response.db_object_exists,
            response.db_object_count,
            response.db_check_ms,
        )
    except Exception as e:
        response.db_check_success = False
        # Don't overwrite error_phase if already set from list
        if not response.error_phase:
            response.error_phase = "db_check"
            response.error_code = type(e).__name__
            response.error_message = str(e)[:200]
        logger.warning("storage_verify: db_check failed: %s", e)
    
    # Phase 3: Delete (cleanup)
    try:
        start = time.perf_counter()
        await client.delete_file(bucket=bucket_name, path=object_key)
        response.delete_ms = round((time.perf_counter() - start) * 1000, 2)
        response.delete_success = True
        logger.info("storage_verify: delete success ms=%.2f", response.delete_ms)
    except Exception as e:
        # Don't fail the whole response, just log
        if not response.error_phase:
            response.error_phase = "delete"
            response.error_code = type(e).__name__
            response.error_message = str(e)[:200]
        logger.warning("storage_verify: delete failed (non-fatal): %s", e, exc_info=True)
    
    # Overall success if upload worked and we found the object (API or DB)
    response.success = response.upload_success and (response.object_found or response.db_object_exists)
    
    logger.info(
        "storage_verify: complete success=%s upload=%s list=%s api_found=%s db_exists=%s delete=%s",
        response.success,
        response.upload_success,
        response.list_success,
        response.object_found,
        response.db_object_exists,
        response.delete_success,
    )
    
    return response
