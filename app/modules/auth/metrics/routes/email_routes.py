# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/routes/email_routes.py

Rutas para métricas de correos del módulo Auth.

Endpoints:
- GET /_internal/auth/metrics/emails: métricas agregadas
- GET /_internal/auth/emails/backlog: lista de pendientes/fallidos

Autor: Sistema
Fecha: 2025-12-26
"""
import logging
from typing import Optional, Literal, List, Any
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.modules.auth.metrics.aggregators.email_aggregators import EmailAggregators

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class EmailMetricsResponse(BaseModel):
    """Métricas agregadas de correos."""
    total_sent: int = Field(..., description="Total de correos enviados (activación + bienvenida)")
    activation_sent: int = Field(..., description="Correos de activación enviados")
    welcome_sent: int = Field(..., description="Correos de bienvenida enviados")
    failed: int = Field(..., description="Correos fallidos (activación + bienvenida)")
    pending: int = Field(..., description="Correos pendientes (activación + bienvenida)")


class BacklogItem(BaseModel):
    """Item del backlog de correos."""
    user_id: str
    email: str
    name: Optional[str] = None
    email_type: str  # activation|welcome
    status: str
    attempts: int
    sent_at: Optional[str] = None
    last_error: Optional[str] = None
    created_at: Optional[str] = None


class BacklogResponse(BaseModel):
    """Respuesta paginada del backlog."""
    items: List[BacklogItem]
    total: int
    page: int
    per_page: int


# ─────────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────────

router = APIRouter(tags=["metrics-auth-emails"])


@router.get("/_internal/auth/metrics/emails", response_model=EmailMetricsResponse)
async def get_email_metrics(db: AsyncSession = Depends(get_db)):
    """
    Obtiene métricas agregadas de correos electrónicos.
    
    Returns:
        EmailMetricsResponse con counts de correos enviados, fallidos y pendientes.
    """
    logger.info("email_metrics_request started")
    
    agg = EmailAggregators(db)
    metrics = await agg.get_email_metrics()
    
    logger.info(
        "email_metrics_request completed: sent=%d failed=%d pending=%d",
        metrics["total_sent"],
        metrics["failed"],
        metrics["pending"],
    )
    
    return EmailMetricsResponse(**metrics)


@router.get("/_internal/auth/emails/backlog", response_model=BacklogResponse)
async def get_email_backlog(
    type: Literal["activation", "welcome", "all"] = Query("all", description="Tipo de correo"),
    status: Literal["pending", "failed"] = Query("pending", description="Estado del correo"),
    page: int = Query(1, ge=1, description="Página"),
    per_page: int = Query(50, ge=1, le=100, description="Items por página"),
    db: AsyncSession = Depends(get_db),
):
    """
    Obtiene lista paginada de correos pendientes o fallidos.
    
    Args:
        type: Tipo de correo (activation, welcome, all)
        status: Estado del correo (pending, failed)
        page: Número de página
        per_page: Items por página
        
    Returns:
        BacklogResponse con lista de items y metadata de paginación.
    """
    logger.info(
        "email_backlog_request started: type=%s status=%s page=%d",
        type,
        status,
        page,
    )
    
    agg = EmailAggregators(db)
    result = await agg.get_backlog(
        email_type=type,
        status=status,
        page=page,
        per_page=per_page,
    )
    
    logger.info(
        "email_backlog_request completed: total=%d items=%d",
        result["total"],
        len(result["items"]),
    )
    
    return BacklogResponse(
        items=[BacklogItem(**item) for item in result["items"]],
        total=result["total"],
        page=result["page"],
        per_page=result["per_page"],
    )


# Fin del archivo
