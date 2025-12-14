
# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/routes/indexing/routes_indexing_reindex.py

Ruteadores para operaciones de reindexación en el módulo RAG.

Uso previsto:
- Reindexar un documento específico (p.ej. tras cambiar el modelo de embeddings).
- Reindexar documentos de un proyecto (p.ej. solo los que no están ready).

Por ahora se implementa una versión mínima que:
- Crea nuevos jobs en rag_jobs para los documentos indicados.
- No ejecuta directamente el pipeline; se espera que un worker/orquestador
  consuma esos jobs.

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from uuid import UUID
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.shared.database.database import get_db
from app.modules.rag.schemas.indexing_schemas import IndexingJobResponse
from app.modules.rag.enums.rag_phase_enum import RagJobPhase

router = APIRouter(tags=["RAG Reindexing"])


@router.post(
    "/rag/indexing/reindex/document/{document_file_id}",
    response_model=IndexingJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Reindexar un documento (crear nuevo job)",
)
async def reindex_document(
    document_file_id: UUID,
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> IndexingJobResponse:
    """
    Crea un nuevo job de indexación RAG para un documento específico.

    No elimina jobs previos; simplemente agrega un job adicional que podrá
    ser ejecutado por el pipeline.
    """
    result = await db.execute(
        text(
            """
            INSERT INTO rag_jobs (
                project_id,
                document_file_id,
                needs_ocr
            )
            VALUES (:project_id, :document_file_id, false)
            RETURNING
                job_id,
                project_id,
                document_file_id,
                status,
                created_at,
                updated_at
            """
        ),
        {
            "project_id": str(project_id),
            "document_file_id": str(document_file_id),
        },
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo crear el job de reindexación.",
        )

    await db.commit()

    return IndexingJobResponse(
        job_id=row["job_id"],
        document_file_id=row["document_file_id"],
        job_phase=RagJobPhase(row["status"]),
        project_id=row["project_id"],
        started_by=None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.post(
    "/rag/indexing/reindex/project/{project_id}",
    response_model=List[IndexingJobResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Reindexar documentos de un proyecto (batch mínimo)",
)
async def reindex_project_documents(
    project_id: UUID,
    only_not_ready: bool = Query(
        default=True,
        description="Si es true, solo reindexa documentos que no están ready.",
    ),
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> List[IndexingJobResponse]:
    """
    Crea jobs de indexación para documentos de un proyecto.

    Implementación mínima:
    - Obtiene documentos desde vw_document_readiness filtrando por project_id.
    - Opcionalmente solo los que no están ready.
    - Crea un job por documento hasta `limit`.
    """
    # Seleccionamos documentos candidatos
    base_query = """
        SELECT document_file_id
        FROM vw_document_readiness
        WHERE project_id = :project_id
    """
    if only_not_ready:
        base_query += " AND NOT is_ready"

    base_query += " LIMIT :limit"

    docs_result = await db.execute(
        text(base_query),
        {"project_id": str(project_id), "limit": limit},
    )
    document_ids = [row["document_file_id"] for row in docs_result.mappings()]

    if not document_ids:
        return []

    jobs: List[IndexingJobResponse] = []

    for document_id in document_ids:
        result = await db.execute(
            text(
                """
                INSERT INTO rag_jobs (
                    project_id,
                    document_file_id,
                    needs_ocr
                )
                VALUES (:project_id, :document_file_id, false)
                RETURNING
                    job_id,
                    project_id,
                    document_file_id,
                    status,
                    created_at,
                    updated_at
                """
            ),
            {
                "project_id": str(project_id),
                "document_file_id": str(document_id),
            },
        )
        row = result.mappings().first()
        if row:
            jobs.append(
                IndexingJobResponse(
                    job_id=row["job_id"],
                    document_file_id=row["document_file_id"],
                    job_phase=RagJobPhase(row["status"]),
                    project_id=row["project_id"],
                    started_by=None,
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )

    await db.commit()
    return jobs


# Fin del archivo backend/app/modules/rag/routes/indexing/routes_indexing_reindex.py
