# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/routes/ocr/routes_ocr_admin.py

Ruteadores administrativos para el subsistema OCR del módulo RAG.

Se apoyan en las vistas:
- vw_ocr_request_summary  → resumen de requests, métricas y costos
- vw_ocr_health           → estado de errores/throttling/queued
- vw_ocr_backlog          → backlog de OCR por documento

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel

from app.shared.database.database import get_db

router = APIRouter(tags=["RAG OCR Admin"])


class OcrRequestSummaryResponse(BaseModel):
    """DTO para vw_ocr_request_summary."""

    ocr_request_id: UUID
    rag_job_id: Optional[UUID] = None
    document_file_id: Optional[UUID] = None
    provider: str
    provider_model: str
    ocr_optimization: str
    status: str
    total_pages: int
    total_characters: int
    latency_ms: Optional[int] = None
    retry_count: int
    cost_total_usd: float
    completed_at: Optional[date] = None


class OcrHealthItemResponse(BaseModel):
    """DTO para vw_ocr_health."""

    ocr_request_id: UUID
    provider: str
    status: str
    retry_count: int
    next_retry_at: Optional[str] = None
    last_error_code: Optional[str] = None
    last_error_message: Optional[str] = None


class OcrBacklogItemResponse(BaseModel):
    """DTO para vw_ocr_backlog."""

    document_file_id: UUID
    needs_ocr: bool
    ocr_state: str
    last_ocr_completed_at: Optional[str] = None
    last_ocr_running_since: Optional[str] = None


@router.get(
    "/rag/ocr/summary",
    response_model=List[OcrRequestSummaryResponse],
    summary="Resumen de requests OCR",
)
async def get_ocr_summary(
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> List[OcrRequestSummaryResponse]:
    """
    Regresa un resumen de solicitudes OCR recientes, con métricas y costos,
    a partir de la vista `vw_ocr_request_summary`.
    """
    result = await db.execute(
        text(
            """
            SELECT
              ocr_request_id,
              rag_job_id,
              document_file_id,
              provider,
              provider_model,
              ocr_optimization,
              status,
              total_pages,
              total_characters,
              latency_ms,
              retry_count,
              cost_total_usd,
              completed_at
            FROM vw_ocr_request_summary
            ORDER BY completed_at DESC NULLS LAST
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )
    rows = result.mappings().all()
    return [
        OcrRequestSummaryResponse(
            ocr_request_id=row["ocr_request_id"],
            rag_job_id=row["rag_job_id"],
            document_file_id=row["document_file_id"],
            provider=row["provider"],
            provider_model=row["provider_model"],
            ocr_optimization=row["ocr_optimization"],
            status=row["status"],
            total_pages=row["total_pages"],
            total_characters=row["total_characters"],
            latency_ms=row["latency_ms"],
            retry_count=row["retry_count"],
            cost_total_usd=float(row["cost_total_usd"]),
            completed_at=row["completed_at"].date() if row["completed_at"] else None,
        )
        for row in rows
    ]


@router.get(
    "/rag/ocr/health",
    response_model=dict,
    summary="Salud y backlog de OCR",
)
async def get_ocr_health(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Regresa un objeto con dos secciones:

    - `issues`: items de vw_ocr_health (failed/throttled/queued)
    - `backlog`: items de vw_ocr_backlog (documentos que requieren OCR)

    Este endpoint está pensado para dashboards de monitoreo y diagnóstico.
    """
    health_result = await db.execute(
        text(
            """
            SELECT
              ocr_request_id,
              provider,
              status,
              retry_count,
              next_retry_at,
              last_error_code,
              last_error_message
            FROM vw_ocr_health
            """
        )
    )
    health_rows = health_result.mappings().all()
    issues = [
        OcrHealthItemResponse(
            ocr_request_id=row["ocr_request_id"],
            provider=row["provider"],
            status=row["status"],
            retry_count=row["retry_count"],
            next_retry_at=(
                row["next_retry_at"].isoformat() if row["next_retry_at"] else None
            ),
            last_error_code=row["last_error_code"],
            last_error_message=row["last_error_message"],
        )
        for row in health_rows
    ]

    backlog_result = await db.execute(
        text(
            """
            SELECT
              document_file_id,
              needs_ocr,
              ocr_state,
              last_ocr_completed_at,
              last_ocr_running_since
            FROM vw_ocr_backlog
            """
        )
    )
    backlog_rows = backlog_result.mappings().all()
    backlog = [
        OcrBacklogItemResponse(
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
        for row in backlog_rows
    ]

    return {"issues": issues, "backlog": backlog}


# Fin del archivo backend/app/modules/rag/routes/ocr/routes_ocr_admin.py
