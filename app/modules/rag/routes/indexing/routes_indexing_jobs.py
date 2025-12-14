
# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/routes/indexing/routes_indexing_jobs.py

Rutas HTTP para gestión de jobs de indexación RAG.

Endpoints:
- POST /rag/projects/{project_id}/jobs/indexing
- GET /rag/jobs/{job_id}/progress
- GET /rag/projects/{project_id}/jobs

Autor: Ixchel Beristain
Fecha: 2025-11-28 (FASE 3 - Implementación completa v2)
"""

from uuid import UUID
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_async_session
from app.modules.files.services.storage_ops_service import AsyncStorageClient
from app.modules.rag.schemas.indexing_schemas import (
    IndexingJobCreate,
    IndexingJobResponse,
    JobProgressResponse,
)
from app.modules.rag.facades.orchestrator_facade import run_indexing_job
from app.modules.rag.repositories.rag_job_repository import RagJobRepository
from app.modules.rag.repositories.rag_job_event_repository import RagJobEventRepository
from app.modules.rag.enums import RagJobPhase

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/rag",
    tags=["rag:indexing"],
)


# ------------------------------------------------------------------------------------
# Dependencia: Storage Client
# ------------------------------------------------------------------------------------

async def get_storage_client() -> AsyncStorageClient:
    """
    Devuelve un cliente de storage que implemente AsyncStorageClient.
    
    IMPORTANTE:
    - En producción, esta dependencia debe ser overrideada con el cliente real.
    - Por defecto devuelve un stub mínimo para permitir tests sin configuración.
    """
    class StubStorageClient:
        async def upload_bytes(self, bucket: str, key: str, data: bytes, mime_type: str | None = None) -> None:
            pass
        async def get_download_url(self, bucket: str, key: str, expires_in_seconds: int = 3600) -> str:
            return f"https://stub-storage/{bucket}/{key}"
        async def delete_object(self, bucket: str, key: str) -> None:
            pass
    return StubStorageClient()  # type: ignore


# ------------------------------------------------------------------------------------
# ENDPOINT: Crear job de indexación
# ------------------------------------------------------------------------------------


@router.post(
    "/projects/{project_id}/jobs/indexing",
    response_model=IndexingJobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_indexing_job(
    project_id: UUID,
    payload: IndexingJobCreate,
    db: AsyncSession = Depends(get_async_session),
    storage_client: AsyncStorageClient = Depends(get_storage_client),
):
    """
    Crea un job de indexación RAG para un archivo.
    
    Flujo:
    1. Valida que project_id coincida con payload
    2. Reserva créditos estimados
    3. Lanza pipeline RAG (convert → ocr? → chunk → embed → integrate → ready)
    4. Retorna detalles del job creado
    
    Nota: El pipeline se ejecuta de forma síncrona en esta implementación.
    En producción considerar background tasks o queue workers.
    """
    if payload.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="project_id in path must match project_id in payload",
        )
    
    logger.info(
        f"[create_indexing_job] Creating RAG job: "
        f"project_id={project_id}, file_id={payload.file_id}, user_id={payload.user_id}"
    )
    
    try:
        # Construir source_uri (formato: bucket/path)
        # Asumimos que el archivo está en users-files bucket
        source_uri = f"users-files/{payload.file_id}"
        
        # Ejecutar pipeline completo
        summary = await run_indexing_job(
            db=db,
            project_id=payload.project_id,
            file_id=payload.file_id,
            user_id=payload.user_id,
            mime_type=payload.mime_type or "application/pdf",
            needs_ocr=payload.needs_ocr,
            storage_client=storage_client,
            source_uri=source_uri,
        )
        
        # Obtener job recién creado
        job_repo = RagJobRepository()
        job = await job_repo.get_by_id(db, summary.job_id)
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve created job",
            )
        
        logger.info(f"[create_indexing_job] Job created successfully: job_id={summary.job_id}")
        
        return IndexingJobResponse(
            job_id=job.job_id,
            project_id=job.project_id,
            started_by=job.created_by,
            phase=job.status,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
        
    except ValueError as ve:
        logger.error(f"[create_indexing_job] Validation error: {ve}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as e:
        logger.error(f"[create_indexing_job] Unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create indexing job: {str(e)}",
        )


@router.get(
    "/jobs/{job_id}/progress",
    response_model=JobProgressResponse,
)
async def get_job_progress(
    job_id: UUID,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Consulta el progreso de un job de indexación.
    
    Returns:
        JobProgressResponse con estado actual, fase, timeline de eventos
    """
    logger.info(f"[get_job_progress] Fetching progress for job_id={job_id}")
    
    try:
        job_repo = RagJobRepository()
        event_repo = RagJobEventRepository()
        
        # Obtener job
        job = await job_repo.get_by_id(db, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found",
            )
        
        # Obtener timeline de eventos
        events = await event_repo.get_timeline(db, job_id, limit=50)
        
        # Calcular progress_pct basado en fase actual
        progress_map = {
            RagJobPhase.queued: 0,
            RagJobPhase.running: 50,
            RagJobPhase.completed: 100,
            RagJobPhase.failed: 0,
            RagJobPhase.cancelled: 0,
        }
        progress_pct = progress_map.get(job.status, 0)
        
        # Determinar finished_at según status
        finished_at = None
        if job.status == RagJobPhase.completed:
            finished_at = job.completed_at
        elif job.status == RagJobPhase.failed:
            finished_at = job.failed_at
        elif job.status == RagJobPhase.cancelled:
            finished_at = job.cancelled_at
        
        return JobProgressResponse(
            job_id=job.job_id,
            project_id=job.project_id,
            file_id=job.file_id,
            phase=job.phase_current,  # RagPhase: convert, ocr, chunk, embed, integrate, ready
            status=job.status,  # RagJobPhase: queued, running, completed, failed, cancelled
            progress_pct=progress_pct,
            started_at=job.created_at,
            finished_at=finished_at,
            updated_at=job.updated_at,
            event_count=len(events),
            timeline=[],  # Opcional: parsear eventos a JobProgressEvent
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[get_job_progress] Unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch job progress: {str(e)}",
        )


@router.get(
    "/projects/{project_id}/jobs",
    response_model=list[JobProgressResponse],
)
async def list_project_jobs(
    project_id: UUID,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Lista los jobs de indexación de un proyecto.
    
    Query params:
        limit: Número máximo de jobs a retornar (default: 50)
        offset: Offset para paginación (default: 0)
    
    Returns:
        Lista de JobProgressResponse
    """
    logger.info(f"[list_project_jobs] Listing jobs for project_id={project_id}, limit={limit}, offset={offset}")
    
    try:
        job_repo = RagJobRepository()
        
        # Obtener jobs del proyecto
        jobs = await job_repo.list_by_project(db, project_id, limit=limit, offset=offset)
        
        # Mapear a response schema
        results = []
        for job in jobs:
            # Determinar finished_at según status
            finished_at = None
            if job.status == RagJobPhase.completed:
                finished_at = job.completed_at
            elif job.status == RagJobPhase.failed:
                finished_at = job.failed_at
            elif job.status == RagJobPhase.cancelled:
                finished_at = job.cancelled_at
            
            # Calcular progress_pct
            progress_map = {
                RagJobPhase.queued: 0,
                RagJobPhase.running: 50,
                RagJobPhase.completed: 100,
                RagJobPhase.failed: 0,
                RagJobPhase.cancelled: 0,
            }
            progress_pct = progress_map.get(job.status, 0)
            
            results.append(
                JobProgressResponse(
                    job_id=job.job_id,
                    project_id=job.project_id,
                    file_id=job.file_id,
                    phase=job.phase_current,  # RagPhase: convert, ocr, chunk, embed, integrate, ready
                    status=job.status,  # RagJobPhase: queued, running, completed, failed, cancelled
                    progress_pct=progress_pct,
                    started_at=job.created_at,
                    finished_at=finished_at,
                    updated_at=job.updated_at,
                    event_count=0,  # No cargamos eventos en lista
                    timeline=[],
                )
            )
        
        logger.info(f"[list_project_jobs] Found {len(results)} jobs for project_id={project_id}")
        
        return results
        
    except Exception as e:
        logger.error(f"[list_project_jobs] Unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list project jobs: {str(e)}",
        )


# Fin del archivo backend/app/modules/rag/routes/indexing/routes_indexing_jobs.py
