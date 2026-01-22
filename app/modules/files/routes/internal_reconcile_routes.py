# -*- coding: utf-8 -*-
"""
backend/app/modules/files/routes/internal_reconcile_routes.py

Endpoint interno para reconciliación de archivos fantasma (DB≠Storage).

POST /_internal/files/reconcile-all
- Ejecuta reconciliación para TODOS los proyectos
- Requiere InternalServiceAuth (APP_SERVICE_TOKEN)
- NO es accesible con JWT de usuario

POST /_internal/files/{project_id}/reconcile-storage
- Ejecuta reconciliación para un proyecto específico
- Requiere InternalServiceAuth (APP_SERVICE_TOKEN)

Autor: DoxAI Team
Fecha: 2026-01-22
"""

from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text, bindparam
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.shared.config import settings
from app.shared.internal_auth import InternalServiceAuth

router = APIRouter(prefix="/_internal/files", tags=["internal:files"])

_logger = logging.getLogger("files.internal.reconcile")


class ReconcileResult(BaseModel):
    """Resultado de reconciliación de storage."""
    
    project_id: Optional[UUID] = Field(None, description="ID del proyecto (si aplica)")
    ghost_files_found: int = Field(..., description="Archivos fantasma detectados")
    ghost_files_archived: int = Field(..., description="Archivos fantasma archivados")
    ghost_file_ids: List[UUID] = Field(default_factory=list, description="IDs de archivos fantasma")
    storage_check_available: bool = Field(
        default=True, 
        description="True si storage.objects fue accesible"
    )


class ReconcileAllResult(BaseModel):
    """Resultado de reconciliación global."""
    
    total_scanned: int = Field(..., description="Total de archivos escaneados")
    ghost_files_found: int = Field(..., description="Archivos fantasma detectados")
    ghost_files_archived: int = Field(..., description="Archivos fantasma archivados")
    affected_project_ids: List[str] = Field(default_factory=list, description="Primeros 10 project_ids afectados")
    storage_check_available: bool = Field(default=True)


async def _check_storage_objects_access(db: AsyncSession, bucket: str) -> bool:
    """Verifica acceso a storage.objects."""
    try:
        result = await db.execute(
            text("SELECT 1 FROM storage.objects WHERE bucket_id = :bucket LIMIT 1"),
            {"bucket": bucket}
        )
        result.fetchone()
        return True
    except Exception as e:
        _logger.warning(
            "storage_objects_access_check_failed: bucket=%s error=%s",
            bucket, str(e)[:200]
        )
        return False


@router.post(
    "/reconcile-all",
    summary="[INTERNAL] Reconciliar todos los archivos fantasma",
    response_model=ReconcileAllResult,
    status_code=status.HTTP_200_OK,
)
async def reconcile_all_storage(
    _auth: InternalServiceAuth,
    db: AsyncSession = Depends(get_db),
    batch_size: int = 500,
) -> ReconcileAllResult:
    """
    Reconcilia TODOS los archivos fantasma de todos los proyectos.
    
    **REQUIERE**: Authorization: Bearer <APP_SERVICE_TOKEN>
    
    Este endpoint es llamado por el job automático o manualmente
    por administradores con acceso al service token.
    """
    bucket_name = getattr(settings, 'supabase_bucket_name', 'users-files')
    
    # Verificar acceso a storage
    storage_accessible = await _check_storage_objects_access(db, bucket_name)
    if not storage_accessible:
        _logger.error("reconcile_all_storage_unavailable: bucket=%s", bucket_name)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "STORAGE_OBJECTS_UNAVAILABLE",
                "message": "No se puede acceder a storage.objects",
            }
        )
    
    # Obtener todos los archivos activos
    active_files_query = await db.execute(
        text("""
            SELECT input_file_id, input_file_storage_path, project_id
            FROM public.input_files
            WHERE input_file_is_active = true
            AND input_file_is_archived = false
            AND input_file_storage_path IS NOT NULL
        """)
    )
    active_files = active_files_query.fetchall()
    
    if not active_files:
        return ReconcileAllResult(
            total_scanned=0,
            ghost_files_found=0,
            ghost_files_archived=0,
            affected_project_ids=[],
            storage_check_available=True,
        )
    
    # Verificar existencia en storage (por batches)
    all_paths = [row[1] for row in active_files if row[1]]
    existing_paths = set()
    
    for i in range(0, len(all_paths), batch_size):
        batch_paths = all_paths[i:i + batch_size]
        if not batch_paths:
            continue
            
        sql = text("""
            SELECT name FROM storage.objects 
            WHERE bucket_id = :bucket AND name IN :paths
        """).bindparams(
            bindparam("bucket"),
            bindparam("paths", expanding=True)
        )
        result = await db.execute(sql, {"bucket": bucket_name, "paths": batch_paths})
        existing_paths.update(row[0] for row in result.fetchall())
    
    # Identificar fantasmas
    ghost_files = [
        (row[0], row[2])  # (input_file_id, project_id)
        for row in active_files
        if row[1] not in existing_paths
    ]
    
    if not ghost_files:
        return ReconcileAllResult(
            total_scanned=len(active_files),
            ghost_files_found=0,
            ghost_files_archived=0,
            affected_project_ids=[],
            storage_check_available=True,
        )
    
    ghost_file_ids = [gf[0] for gf in ghost_files]
    affected_project_ids = list(set(str(gf[1])[:8] for gf in ghost_files))[:10]
    
    # Archivar fantasmas
    archive_sql = text("""
        UPDATE public.input_files
        SET input_file_is_active = false,
            input_file_is_archived = true,
            updated_at = now()
        WHERE input_file_id IN :ids
    """).bindparams(
        bindparam("ids", expanding=True)
    )
    await db.execute(archive_sql, {"ids": ghost_file_ids})
    await db.commit()
    
    _logger.info(
        "reconcile_all_done: scanned=%d ghosts=%d archived=%d projects=%s",
        len(active_files),
        len(ghost_files),
        len(ghost_file_ids),
        affected_project_ids,
    )
    
    return ReconcileAllResult(
        total_scanned=len(active_files),
        ghost_files_found=len(ghost_files),
        ghost_files_archived=len(ghost_file_ids),
        affected_project_ids=affected_project_ids,
        storage_check_available=True,
    )


@router.post(
    "/{project_id}/reconcile-storage",
    summary="[INTERNAL] Reconciliar archivos fantasma de un proyecto",
    response_model=ReconcileResult,
    status_code=status.HTTP_200_OK,
)
async def reconcile_project_storage(
    project_id: UUID,
    _auth: InternalServiceAuth,
    db: AsyncSession = Depends(get_db),
) -> ReconcileResult:
    """
    Reconcilia archivos fantasma de un proyecto específico.
    
    **REQUIERE**: Authorization: Bearer <APP_SERVICE_TOKEN>
    
    Solo para uso interno (service token), no por usuarios.
    """
    bucket_name = getattr(settings, 'supabase_bucket_name', 'users-files')
    
    # Verificar que el proyecto existe
    project_check = await db.execute(
        text("SELECT id FROM public.projects WHERE id = CAST(:project_id AS uuid)"),
        {"project_id": str(project_id)}
    )
    if not project_check.fetchone():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proyecto no encontrado"
        )
    
    # Verificar acceso a storage
    storage_accessible = await _check_storage_objects_access(db, bucket_name)
    if not storage_accessible:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "STORAGE_OBJECTS_UNAVAILABLE",
                "message": "No se puede acceder a storage.objects",
            }
        )
    
    # Obtener archivos activos del proyecto
    active_files_query = await db.execute(
        text("""
            SELECT input_file_id, input_file_storage_path
            FROM public.input_files
            WHERE project_id = CAST(:project_id AS uuid)
            AND input_file_is_active = true
            AND input_file_is_archived = false
        """),
        {"project_id": str(project_id)}
    )
    active_files = active_files_query.fetchall()
    
    if not active_files:
        return ReconcileResult(
            project_id=project_id,
            ghost_files_found=0,
            ghost_files_archived=0,
            ghost_file_ids=[],
            storage_check_available=True,
        )
    
    # Verificar existencia en storage
    all_paths = [row[1] for row in active_files if row[1]]
    
    if not all_paths:
        return ReconcileResult(
            project_id=project_id,
            ghost_files_found=0,
            ghost_files_archived=0,
            ghost_file_ids=[],
            storage_check_available=True,
        )
    
    sql = text("""
        SELECT name FROM storage.objects 
        WHERE bucket_id = :bucket AND name IN :paths
    """).bindparams(
        bindparam("bucket"),
        bindparam("paths", expanding=True)
    )
    result = await db.execute(sql, {"bucket": bucket_name, "paths": all_paths})
    existing_paths = {row[0] for row in result.fetchall()}
    
    # Identificar y archivar fantasmas
    ghost_files = [
        row[0] for row in active_files if row[1] not in existing_paths
    ]
    
    if not ghost_files:
        return ReconcileResult(
            project_id=project_id,
            ghost_files_found=0,
            ghost_files_archived=0,
            ghost_file_ids=[],
            storage_check_available=True,
        )
    
    archive_sql = text("""
        UPDATE public.input_files
        SET input_file_is_active = false,
            input_file_is_archived = true,
            updated_at = now()
        WHERE input_file_id IN :ids
    """).bindparams(
        bindparam("ids", expanding=True)
    )
    await db.execute(archive_sql, {"ids": ghost_files})
    await db.commit()
    
    _logger.info(
        "reconcile_project_done: project=%s ghosts=%d",
        str(project_id)[:8],
        len(ghost_files),
    )
    
    return ReconcileResult(
        project_id=project_id,
        ghost_files_found=len(ghost_files),
        ghost_files_archived=len(ghost_files),
        ghost_file_ids=ghost_files,
        storage_check_available=True,
    )


__all__ = ["router"]

# Fin del archivo
