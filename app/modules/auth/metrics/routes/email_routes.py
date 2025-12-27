# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/routes/email_routes.py

Rutas para métricas de correos del módulo Auth.

Endpoints:
- GET /_internal/auth/metrics/emails: métricas agregadas
- GET /_internal/auth/emails/backlog: lista de pendientes/fallidos
- POST /_internal/auth/emails/{type}/{user_id}/retry: reintentar envío (stub)

Autor: Sistema
Fecha: 2025-12-26
"""
import logging
from typing import Optional, Literal, List, Any
from fastapi import APIRouter, Depends, Query, Path, HTTPException
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
    # Welcome latency (top-level, sin SLA/ventana)
    welcome_latency_count: int = Field(0, description="Usuarios con welcome email enviado")
    welcome_latency_avg_ms: Optional[float] = Field(None, description="Latencia promedio en ms")
    welcome_latency_p50_ms: Optional[float] = Field(None, description="Latencia p50 en ms")
    welcome_latency_p90_ms: Optional[float] = Field(None, description="Latencia p90 en ms")
    welcome_latency_p95_ms: Optional[float] = Field(None, description="Latencia p95 en ms")


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


class RetryResponse(BaseModel):
    """Respuesta del endpoint de reintento."""
    accepted: bool = Field(..., description="Si el reintento fue aceptado")
    message: str = Field(..., description="Mensaje descriptivo")
    user_id: str = Field(..., description="ID del usuario")
    email_type: str = Field(..., description="Tipo de correo")


# ─────────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────────

router = APIRouter(tags=["metrics-auth-emails"])


@router.get("/_internal/auth/metrics/emails", response_model=EmailMetricsResponse)
async def get_email_metrics(db: AsyncSession = Depends(get_db)):
    """
    Obtiene métricas agregadas de correos electrónicos.
    
    Returns:
        EmailMetricsResponse con counts de correos enviados, fallidos, pendientes
        y latencia de welcome emails.
    """
    logger.info("email_metrics_request started")
    
    agg = EmailAggregators(db)
    metrics = await agg.get_email_metrics()
    
    logger.info(
        "email_metrics_request completed: sent=%d failed=%d pending=%d latency_count=%d",
        metrics["total_sent"],
        metrics["failed"],
        metrics["pending"],
        metrics.get("welcome_latency_count", 0),
    )
    
    return EmailMetricsResponse(
        total_sent=metrics["total_sent"],
        activation_sent=metrics["activation_sent"],
        welcome_sent=metrics["welcome_sent"],
        failed=metrics["failed"],
        pending=metrics["pending"],
        welcome_latency_count=metrics.get("welcome_latency_count", 0),
        welcome_latency_avg_ms=metrics.get("welcome_latency_avg_ms"),
        welcome_latency_p50_ms=metrics.get("welcome_latency_p50_ms"),
        welcome_latency_p90_ms=metrics.get("welcome_latency_p90_ms"),
        welcome_latency_p95_ms=metrics.get("welcome_latency_p95_ms"),
    )


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


@router.post(
    "/_internal/auth/emails/{email_type}/{user_id}/retry",
    response_model=RetryResponse,
)
async def retry_email(
    email_type: Literal["activation", "welcome"] = Path(
        ..., description="Tipo de correo"
    ),
    user_id: str = Path(..., description="ID del usuario"),
    db: AsyncSession = Depends(get_db),
):
    """
    Endpoint stub para reintentar envío de correo.
    
    Actualmente solo registra la solicitud y devuelve éxito.
    La lógica real de reintento se implementará en una fase posterior.
    
    Args:
        email_type: Tipo de correo (activation o welcome)
        user_id: ID del usuario
        
    Returns:
        RetryResponse indicando que el reintento fue programado.
    """
    logger.info(
        "email_retry_request received: type=%s user_id=%s",
        email_type,
        user_id,
    )
    
    # TODO: Implementar lógica real de reintento
    # Por ahora solo es un stub que acepta la solicitud
    
    logger.info(
        "email_retry_request accepted (stub): type=%s user_id=%s",
        email_type,
        user_id,
    )
    
    return RetryResponse(
        accepted=True,
        message="Reintento programado (pendiente de implementación)",
        user_id=user_id,
        email_type=email_type,
    )


# Fin del archivo
