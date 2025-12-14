
# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/routes/diagnostics/routes_diagnostics.py

Ruteadores de diagnóstico para el módulo RAG.

En lugar de exponer directamente los scripts de diagnóstico ad-hoc, se
apoyan en vistas estables que ya existen en la base de datos, como:

- vw_pipeline_efficiency
- vw_ocr_backlog

Estos endpoints son útiles para:
- Soporte técnico.
- Auditorías del pipeline.
- Verificación de latencias y backlog.

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel

from app.shared.database.database import get_db

router = APIRouter(tags=["RAG Diagnostics"])


class PipelineEfficiencyItem(BaseModel):
    """DTO para filas de vw_pipeline_efficiency."""

    job_id: UUID
    document_file_id: UUID
    job_started_at: str | None = None
    ocr_started_at: str | None = None
    ocr_completed_at: str | None = None
    last_embedding_at: str | None = None
    sec_convert_to_ocr: int | None = None
    sec_ocr_duration: int | None = None
    sec_ocr_to_embed: int | None = None


class OcrBacklogDiagnosticItem(BaseModel):
    """DTO para vw_ocr_backlog (reutilizado en diagnóstico)."""

    document_file_id: UUID
    needs_ocr: bool
    ocr_state: str
    last_ocr_completed_at: str | None = None
    last_ocr_running_since: str | None = None


@router.get(
    "/rag/diagnostics/pipeline-efficiency",
    response_model=List[PipelineEfficiencyItem],
    summary="Diagnóstico de latencias del pipeline",
)
async def diagnostics_pipeline_efficiency(
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> List[PipelineEfficiencyItem]:
    """
    Regresa filas de la vista `vw_pipeline_efficiency`, útiles para
    analizar latencias entre las fases convert → OCR → embed.
    """
    result = await db.execute(
        text(
            """
            SELECT
              job_id,
              document_file_id,
              job_started_at,
              ocr_started_at,
              ocr_completed_at,
              last_embedding_at,
              sec_convert_to_ocr,
              sec_ocr_duration,
              sec_ocr_to_embed
            FROM vw_pipeline_efficiency
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )
    rows = result.mappings().all()
    return [
        PipelineEfficiencyItem(
            job_id=row["job_id"],
            document_file_id=row["document_file_id"],
            job_started_at=row["job_started_at"].isoformat()
            if row["job_started_at"]
            else None,
            ocr_started_at=row["ocr_started_at"].isoformat()
            if row["ocr_started_at"]
            else None,
            ocr_completed_at=row["ocr_completed_at"].isoformat()
            if row["ocr_completed_at"]
            else None,
            last_embedding_at=row["last_embedding_at"].isoformat()
            if row["last_embedding_at"]
            else None,
            sec_convert_to_ocr=row["sec_convert_to_ocr"],
            sec_ocr_duration=row["sec_ocr_duration"],
            sec_ocr_to_embed=row["sec_ocr_to_embed"],
        )
        for row in rows
    ]


@router.get(
    "/rag/diagnostics/ocr-backlog",
    response_model=List[OcrBacklogDiagnosticItem],
    summary="Diagnóstico de backlog OCR",
)
async def diagnostics_ocr_backlog(
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> List[OcrBacklogDiagnosticItem]:
    """
    Regresa filas de `vw_ocr_backlog`, que identifican documentos con
    necesidad de OCR y su estado operativo.
    """
    result = await db.execute(
        text(
            """
            SELECT
              document_file_id,
              needs_ocr,
              ocr_state,
              last_ocr_completed_at,
              last_ocr_running_since
            FROM vw_ocr_backlog
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )
    rows = result.mappings().all()
    return [
        OcrBacklogDiagnosticItem(
            document_file_id=row["document_file_id"],
            needs_ocr=row["needs_ocr"],
            ocr_state=row["ocr_state"],
            last_ocr_completed_at=(
                row["last_ocr_completed_at"].isoformat()
                if row["last_ocr_completed_at"]
                else None
            ),
            last_ocr_running_since=(
                row["last_ocr_running_since"].isoformat()
                if row["last_ocr_running_since"]
                else None
            ),
        )
        for row in rows
    ]


# Fin del archivo backend/app/modules/rag/routes/diagnostics/routes_diagnostics.py
