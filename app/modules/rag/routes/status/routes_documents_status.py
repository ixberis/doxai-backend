# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/routes/status/routes_documents_status.py

Rutas HTTP para consultar el estado de documentos indexados.

Endpoints:
- GET /rag/documents/{file_id}/status

Autor: Ixchel Beristain
Fecha: 2025-11-28 (FASE 3 - Implementación completa v2)
"""

from uuid import UUID
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.shared.database.database import get_async_session
from app.modules.rag.repositories.document_embedding_repository import DocumentEmbeddingRepository
from app.modules.rag.enums import RagJobPhase, RagPhase

logger = logging.getLogger(__name__)


class DocumentStatusResponse(BaseModel):
    """Schema de respuesta para estado de documento."""
    file_id: UUID
    is_ready: bool
    last_job_id: UUID | None = None
    last_status: RagJobPhase | None = None
    last_phase: RagPhase | None = None
    active_embeddings_count: int = 0


router = APIRouter(
    prefix="/rag/documents",
    tags=["rag:status"],
)


@router.get(
    "/{file_id}/status",
    response_model=DocumentStatusResponse,
)
async def get_document_status(
    file_id: UUID,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Consulta el estado de un documento indexado.
    
    Returns:
        DocumentStatusResponse con información de indexación y embeddings
    """
    logger.info(f"[get_document_status] Checking status for file_id={file_id}")
    
    try:
        embedding_repo = DocumentEmbeddingRepository()
        
        # Contar embeddings activos
        active_count = await embedding_repo.count_by_file(db, file_id, active_only=True)
        
        is_ready = (active_count > 0)
        
        logger.info(f"[get_document_status] file_id={file_id}: is_ready={is_ready}, active_embeddings={active_count}")
        
        return DocumentStatusResponse(
            file_id=file_id,
            is_ready=is_ready,
            last_job_id=None,
            last_status=None,
            last_phase=None,
            active_embeddings_count=active_count,
        )
        
    except Exception as e:
        logger.error(f"[get_document_status] Unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch document status: {str(e)}",
        )


# Fin del archivo backend/app/modules/rag/routes/status/routes_documents_status.py
