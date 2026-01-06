# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/routes/functional_routes.py

Rutas para métricas de Auth Funcional con soporte de rango.

Endpoints:
- GET /_internal/auth/metrics/activation: métricas de activación por rango
- GET /_internal/auth/metrics/password-resets: métricas de password reset por rango
- GET /_internal/auth/metrics/users: lista de usuarios por rango (paginada)

Autor: Sistema
Fecha: 2026-01-04
"""
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.modules.auth.metrics.aggregators.functional_aggregators import FunctionalAggregators

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/_internal/auth/metrics", tags=["metrics-auth-functional"])


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class ActivationMetricsResponse(BaseModel):
    """Respuesta de métricas de activación."""
    activation_emails_sent: int = Field(..., description="Emails de activación enviados en el periodo")
    activations_completed: int = Field(..., description="Activaciones completadas en el periodo")
    resends: int = Field(..., description="Reenvíos de email en el periodo")
    tokens_expired: int = Field(..., description="Tokens expirados sin usar")
    completion_rate: Optional[float] = Field(None, description="Tasa de completado (activaciones/emails)")
    avg_time_to_activate_seconds: Optional[float] = Field(None, description="Tiempo promedio de activación")
    sample_count: int = Field(0, description="Muestra de latencia")
    from_date: str = Field(..., description="Fecha inicio (YYYY-MM-DD)")
    to_date: str = Field(..., description="Fecha fin (YYYY-MM-DD)")
    generated_at: str = Field(..., description="Timestamp de generación")
    # Campos de trazabilidad
    email_events_source: str = Field("none", description="Fuente de datos: instrumented | fallback | none")
    email_events_partial: bool = Field(False, description="True si los datos de emails son estimados (fallback)")


class PasswordResetMetricsResponse(BaseModel):
    """Respuesta de métricas de password reset."""
    requests_total: int = Field(..., description="Solicitudes de reset en el periodo")
    completed_total: int = Field(..., description="Resets completados en el periodo")
    tokens_expired: int = Field(..., description="Tokens expirados sin usar")
    abandon_rate: Optional[float] = Field(None, description="Tasa de abandono")
    completion_rate: Optional[float] = Field(None, description="Tasa de completado")
    avg_time_seconds: Optional[float] = Field(None, description="Tiempo promedio de completar reset")
    sample_count: int = Field(0, description="Muestra de latencia")
    from_date: str = Field(..., description="Fecha inicio (YYYY-MM-DD)")
    to_date: str = Field(..., description="Fecha fin (YYYY-MM-DD)")
    generated_at: str = Field(..., description="Timestamp de generación")


class UsersAnalyticsResponse(BaseModel):
    """Respuesta de métricas analíticas de usuarios."""
    # Periodo
    created_in_period: int = Field(..., description="Usuarios creados en el periodo")
    activated_in_period: int = Field(..., description="Usuarios activados en el periodo")
    deleted_in_period: int = Field(..., description="Usuarios eliminados en el periodo")
    # Stock (estado actual)
    activated_stock: int = Field(0, description="Usuarios actualmente activados")
    active_stock: int = Field(0, description="Usuarios activos")
    suspended_stock: int = Field(0, description="Usuarios suspendidos")
    deleted_stock: int = Field(0, description="Usuarios eliminados")
    # Calidad de activación
    not_activated_24h: int = Field(0, description="Usuarios no activados tras 24h")
    activation_time_p95_hours: Optional[float] = Field(None, description="P95 tiempo de activación (horas)")
    activation_retries: int = Field(0, description="Usuarios con reintentos de activación")
    activation_retries_instrumented: bool = Field(False, description="True si activation_retries tiene datos instrumentados")
    # Conversión
    activation_rate: Optional[float] = Field(None, description="Tasa de activación (activados/creados)")
    activated_no_session: int = Field(0, description="Activados sin sesión (stock)")
    activated_no_session_in_period: int = Field(0, description="Activados en periodo sin sesión aún")
    # Estados críticos
    suspended_created_in_period: int = Field(0, description="Suspendidos creados en periodo")
    deleted_not_activated: int = Field(0, description="Eliminados sin activar (histórico)")
    deleted_not_activated_in_period: int = Field(0, description="Eliminados en periodo sin activar")
    # Metadata
    from_date: str
    to_date: str
    generated_at: str


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_date(date_str: Optional[str], param_name: str, default_offset_days: int = 0) -> date:
    """Parse date string or use default."""
    if date_str:
        try:
            return date.fromisoformat(date_str)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Formato de fecha '{param_name}' inválido: {date_str}. Usar YYYY-MM-DD"
            )
    return date.today() - timedelta(days=default_offset_days)


def _validate_range(from_dt: date, to_dt: date, max_days: int = 365):
    """Validate date range."""
    if from_dt > to_dt:
        raise HTTPException(
            status_code=400,
            detail=f"'from' ({from_dt}) debe ser <= 'to' ({to_dt})"
        )
    if (to_dt - from_dt).days > max_days:
        raise HTTPException(
            status_code=400,
            detail=f"Rango máximo permitido: {max_days} días"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/activation", response_model=ActivationMetricsResponse)
async def get_activation_metrics(
    from_date: Optional[str] = Query(None, alias="from", description="Fecha inicio (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, alias="to", description="Fecha fin (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Obtiene métricas de activación para un rango de fechas.
    
    Si no se especifican fechas, usa los últimos 30 días.
    """
    to_dt = _parse_date(to_date, "to", default_offset_days=0)
    from_dt = _parse_date(from_date, "from", default_offset_days=30) if from_date else (to_dt - timedelta(days=30))
    _validate_range(from_dt, to_dt)
    
    logger.info("activation_metrics_request from=%s to=%s", from_dt, to_dt)
    
    try:
        agg = FunctionalAggregators(db)
        metrics = await agg.get_activation_metrics(from_dt, to_dt)
        
        return ActivationMetricsResponse(
            activation_emails_sent=metrics.activation_emails_sent,
            activations_completed=metrics.activations_completed,
            resends=metrics.resends,
            tokens_expired=metrics.tokens_expired,
            completion_rate=metrics.completion_rate,
            avg_time_to_activate_seconds=metrics.avg_time_to_activate_seconds,
            sample_count=metrics.sample_count,
            from_date=metrics.from_date,
            to_date=metrics.to_date,
            generated_at=metrics.generated_at,
            email_events_source=metrics.email_events_source,
            email_events_partial=metrics.email_events_partial,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("activation_metrics_request failed: %s", e)
        raise HTTPException(status_code=500, detail="Error al obtener métricas de activación")


@router.get("/password-resets", response_model=PasswordResetMetricsResponse)
async def get_password_reset_metrics(
    from_date: Optional[str] = Query(None, alias="from", description="Fecha inicio (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, alias="to", description="Fecha fin (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Obtiene métricas de password reset para un rango de fechas.
    
    Si no se especifican fechas, usa los últimos 30 días.
    """
    to_dt = _parse_date(to_date, "to", default_offset_days=0)
    from_dt = _parse_date(from_date, "from", default_offset_days=30) if from_date else (to_dt - timedelta(days=30))
    _validate_range(from_dt, to_dt)
    
    logger.info("password_reset_metrics_request from=%s to=%s", from_dt, to_dt)
    
    try:
        agg = FunctionalAggregators(db)
        metrics = await agg.get_password_reset_metrics(from_dt, to_dt)
        
        return PasswordResetMetricsResponse(
            requests_total=metrics.requests_total,
            completed_total=metrics.completed_total,
            tokens_expired=metrics.tokens_expired,
            abandon_rate=metrics.abandon_rate,
            completion_rate=metrics.completion_rate,
            avg_time_seconds=metrics.avg_time_seconds,
            sample_count=metrics.sample_count,
            from_date=metrics.from_date,
            to_date=metrics.to_date,
            generated_at=metrics.generated_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("password_reset_metrics_request failed: %s", e)
        raise HTTPException(status_code=500, detail="Error al obtener métricas de password reset")


@router.get("/users", response_model=UsersAnalyticsResponse)
async def get_users_analytics(
    from_date: Optional[str] = Query(None, alias="from", description="Fecha inicio (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, alias="to", description="Fecha fin (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Obtiene métricas analíticas de usuarios por rango de fechas.
    
    Incluye métricas de calidad de activación, conversión y estados críticos.
    No devuelve lista individual de usuarios (ver Admin -> Users para eso).
    """
    to_dt = _parse_date(to_date, "to", default_offset_days=0)
    from_dt = _parse_date(from_date, "from", default_offset_days=30) if from_date else (to_dt - timedelta(days=30))
    _validate_range(from_dt, to_dt)
    
    logger.info("users_analytics_request from=%s to=%s", from_dt, to_dt)
    
    try:
        agg = FunctionalAggregators(db)
        metrics = await agg.get_users_analytics(from_dt, to_dt)
        
        return UsersAnalyticsResponse(
            created_in_period=metrics.created_in_period,
            activated_in_period=metrics.activated_in_period,
            deleted_in_period=metrics.deleted_in_period,
            activated_stock=metrics.activated_stock,
            active_stock=metrics.active_stock,
            suspended_stock=metrics.suspended_stock,
            deleted_stock=metrics.deleted_stock,
            not_activated_24h=metrics.not_activated_24h,
            activation_time_p95_hours=metrics.activation_time_p95_hours,
            activation_retries=metrics.activation_retries,
            activation_retries_instrumented=metrics.activation_retries_instrumented,
            activation_rate=metrics.activation_rate,
            activated_no_session=metrics.activated_no_session,
            activated_no_session_in_period=metrics.activated_no_session_in_period,
            suspended_created_in_period=metrics.suspended_created_in_period,
            deleted_not_activated=metrics.deleted_not_activated,
            deleted_not_activated_in_period=metrics.deleted_not_activated_in_period,
            from_date=metrics.from_date,
            to_date=metrics.to_date,
            generated_at=metrics.generated_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("users_analytics_request failed: %s", e)
        raise HTTPException(status_code=500, detail="Error al obtener métricas de usuarios")


# Fin del archivo
