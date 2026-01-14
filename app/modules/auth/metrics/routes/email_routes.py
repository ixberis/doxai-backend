# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/routes/email_routes.py

Rutas para métricas de correos del módulo Auth.

Endpoints:
- GET /_internal/auth/metrics/emails: métricas agregadas (global)
- GET /_internal/auth/metrics/emails/by-type: métricas por tipo de email
- GET /_internal/auth/emails/backlog: lista de pendientes/fallidos
- POST /_internal/auth/emails/{type}/{user_id}/retry: reintentar envío (stub)

Autor: Sistema
Fecha: 2025-12-26
Actualizado: 2026-01-07 - Renombrar sent_total a outbound_total (semántica correcta)
"""
import logging
import uuid
from datetime import date, timedelta
from typing import Optional, Literal, List, Any
from fastapi import APIRouter, Depends, Query, Path, HTTPException
from pydantic import BaseModel, Field

from app.modules.auth.dependencies import require_admin_strict
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.modules.auth.metrics.aggregators.email_aggregators import EmailAggregators
from app.modules.auth.metrics.aggregators.email_by_type_aggregators import EmailByTypeAggregators

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


class EmailTypeMetrics(BaseModel):
    """Métricas para un tipo de email específico."""
    email_type: str = Field(..., description="Tipo de email")
    outbound_total: int = Field(..., description="Emails enviados al proveedor (sent/delivered/bounced/complained)")
    failed_total: int = Field(..., description="Emails fallidos antes de envío")
    pending_total: int = Field(..., description="Emails pendientes")
    failure_rate: float = Field(..., description="Tasa de fallo (fallidos / total intentos)")
    latency_avg_ms: Optional[float] = Field(None, description="Latencia promedio en ms")
    latency_p95_ms: Optional[float] = Field(None, description="Latencia p95 en ms")
    latency_count: int = Field(0, description="Muestra de latencia")


class EmailTotals(BaseModel):
    """Totales agregados de todos los tipos."""
    outbound_total: int
    failed_total: int
    pending_total: int
    failure_rate: float
    latency_avg_ms: Optional[float] = None
    latency_p95_ms: Optional[float] = None
    latency_count: int = 0


class EmailMetricsByTypeResponse(BaseModel):
    """Respuesta de métricas por tipo de email."""
    period_from: str = Field(..., description="Fecha inicio del periodo (YYYY-MM-DD)")
    period_to: str = Field(..., description="Fecha fin del periodo (YYYY-MM-DD)")
    generated_at: str = Field(..., description="Timestamp de generación (ISO 8601)")
    items: List[EmailTypeMetrics] = Field(..., description="Métricas por tipo")
    totals: EmailTotals = Field(..., description="Totales agregados")
    has_data: bool = Field(True, description="True si hay datos reales en el periodo")
    note: Optional[str] = Field(None, description="Nota explicativa cuando has_data=False")


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


@router.get(
    "/_internal/admin/auth/email-metrics/by-type",
    response_model=EmailMetricsByTypeResponse,
    dependencies=[Depends(require_admin_strict)],
)
async def get_email_metrics_by_type(
    from_date: Optional[str] = Query(
        None, 
        alias="from",
        description="Fecha inicio (YYYY-MM-DD). Default: 30 días atrás"
    ),
    to_date: Optional[str] = Query(
        None,
        alias="to", 
        description="Fecha fin (YYYY-MM-DD). Default: hoy"
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Obtiene métricas de correos desglosadas por tipo.
    
    Soporta filtro por periodo (from/to, ambos inclusive).
    Si no se especifica, usa los últimos 30 días.
    
    Returns:
        EmailMetricsByTypeResponse con items por tipo y totales.
        
    Nota sobre outbound_total:
        Cuenta correos en estado sent, delivered, bounced, o complained.
        Esto refleja todos los correos que llegaron al proveedor (MailerSend),
        independiente del resultado final de entrega.
    """
    # Parse dates
    today = date.today()
    
    if to_date:
        try:
            to_dt = date.fromisoformat(to_date)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Formato de fecha 'to' inválido: {to_date}. Usar YYYY-MM-DD"
            )
    else:
        to_dt = today
    
    if from_date:
        try:
            from_dt = date.fromisoformat(from_date)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Formato de fecha 'from' inválido: {from_date}. Usar YYYY-MM-DD"
            )
    else:
        from_dt = to_dt - timedelta(days=30)
    
    # Validate range
    if from_dt > to_dt:
        raise HTTPException(
            status_code=400,
            detail=f"'from' ({from_dt}) debe ser <= 'to' ({to_dt})"
        )
    
    max_range_days = 365
    if (to_dt - from_dt).days > max_range_days:
        raise HTTPException(
            status_code=400,
            detail=f"Rango máximo permitido: {max_range_days} días"
        )
    
    request_id = str(uuid.uuid4())[:8]
    
    logger.info(
        "email_metrics_by_type_request: request_id=%s from=%s to=%s",
        request_id,
        from_dt.isoformat(),
        to_dt.isoformat(),
    )
    
    try:
        agg = EmailByTypeAggregators(db)
        result = await agg.get_metrics_by_type(from_dt, to_dt)
        
        # Check if we have any real data
        total_events = result["totals"]["outbound_total"] + result["totals"]["failed_total"] + result["totals"]["pending_total"]
        has_data = total_events > 0
        note = None if has_data else "No se registraron eventos de correo en el periodo seleccionado."
        
        logger.info(
            "email_metrics_by_type_completed: request_id=%s items=%d outbound=%d failed=%d pending=%d has_data=%s",
            request_id,
            len(result["items"]),
            result["totals"]["outbound_total"],
            result["totals"]["failed_total"],
            result["totals"]["pending_total"],
            has_data,
        )
        
        return EmailMetricsByTypeResponse(
            period_from=result["period_from"],
            period_to=result["period_to"],
            generated_at=result["generated_at"],
            items=[EmailTypeMetrics(**item) for item in result["items"]],
            totals=EmailTotals(**result["totals"]),
            has_data=has_data,
            note=note,
        )
    except Exception:
        logger.exception("email_metrics_by_type_error: request_id=%s", request_id)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Error al obtener métricas de correo por tipo",
                "request_id": request_id,
            }
        )


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
