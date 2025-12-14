
# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/routes/status/routes_projects_status.py

Ruteadores para exponer el estado agregado de RAG por proyecto, usando
las vistas materializadas de KPIs en el esquema `kpis`:

- kpis.mv_rag_document_readiness
- kpis.mv_rag_embedding_coverage

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from uuid import UUID
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.shared.database.database import get_db
from pydantic import BaseModel


class ProjectRagStatusResponse(BaseModel):
    """
    Estado agregado RAG de un proyecto.

    Integra:
    - Número total de documentos.
    - Documentos ready.
    - Porcentaje de readiness.
    - Cobertura de embeddings (% de documentos con embeddings activos).
    """

    project_id: UUID
    documents_total: int
    documents_ready: int
    documents_not_ready: int
    readiness_pct: float
    embedding_coverage_pct: float | None = None


router = APIRouter(tags=["RAG Status - Projects"])


@router.get(
    "/rag/status/projects/{project_id}",
    response_model=ProjectRagStatusResponse,
    summary="Estado RAG de un proyecto",
)
async def get_project_rag_status(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ProjectRagStatusResponse:
    """
    Regresa el estado agregado RAG para un proyecto específico, combinando
    KPIs de readiness y cobertura de embeddings.
    """
    result = await db.execute(
        text(
            """
            SELECT
              d.project_id,
              d.documents_total,
              d.documents_ready,
              d.documents_not_ready,
              d.readiness_pct,
              c.embedding_coverage_pct
            FROM kpis.mv_rag_document_readiness d
            LEFT JOIN kpis.mv_rag_embedding_coverage c
              ON c.project_id = d.project_id
            WHERE d.project_id = :project_id
            """
        ),
        {"project_id": str(project_id)},
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Proyecto {project_id} no encontrado en KPIs RAG.",
        )

    return ProjectRagStatusResponse(
        project_id=row["project_id"],
        documents_total=row["documents_total"],
        documents_ready=row["documents_ready"],
        documents_not_ready=row["documents_not_ready"],
        readiness_pct=float(row["readiness_pct"]),
        embedding_coverage_pct=(
            float(row["embedding_coverage_pct"])
            if row["embedding_coverage_pct"] is not None
            else None
        ),
    )


@router.get(
    "/rag/status/projects",
    response_model=List[ProjectRagStatusResponse],
    summary="Listado de proyectos con estado RAG",
)
async def list_projects_rag_status(
    min_readiness_pct: float = Query(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Filtrar proyectos con readiness_pct >= este valor.",
    ),
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> List[ProjectRagStatusResponse]:
    """
    Lista proyectos con sus KPIs RAG principales.

    Permite filtrar por un mínimo de readiness_pct y limitar el número de
    resultados.
    """
    result = await db.execute(
        text(
            """
            SELECT
              d.project_id,
              d.documents_total,
              d.documents_ready,
              d.documents_not_ready,
              d.readiness_pct,
              c.embedding_coverage_pct
            FROM kpis.mv_rag_document_readiness d
            LEFT JOIN kpis.mv_rag_embedding_coverage c
              ON c.project_id = d.project_id
            WHERE d.readiness_pct >= :min_readiness_pct
            ORDER BY d.readiness_pct ASC
            LIMIT :limit
            """
        ),
        {"min_readiness_pct": min_readiness_pct, "limit": limit},
    )
    rows = result.mappings().all()

    return [
        ProjectRagStatusResponse(
            project_id=row["project_id"],
            documents_total=row["documents_total"],
            documents_ready=row["documents_ready"],
            documents_not_ready=row["documents_not_ready"],
            readiness_pct=float(row["readiness_pct"]),
            embedding_coverage_pct=(
                float(row["embedding_coverage_pct"])
                if row["embedding_coverage_pct"] is not None
                else None
            ),
        )
        for row in rows
    ]


# Fin del archivo backend/app/modules/rag/routes/status/routes_projects_status.py
