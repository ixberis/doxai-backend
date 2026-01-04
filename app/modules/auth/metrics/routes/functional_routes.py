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
from typing import Optional, List

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


class UserListItem(BaseModel):
    """Usuario en la lista."""
    user_id: str
    email_masked: str = Field(..., description="Email parcialmente enmascarado")
    full_name: Optional[str] = None
    status: str = Field(..., description="active | suspended | deleted")
    is_activated: bool
    created_at: str
    activated_at: Optional[str] = None
    last_login_at: Optional[str] = None


class UsersMetricsResponse(BaseModel):
    """Respuesta de usuarios con paginación."""
    users: List[UserListItem]
    total: int = Field(..., description="Total de usuarios en el periodo")
    page: int
    page_size: int
    # Totals for period
    created_in_period: int = Field(..., description="Usuarios creados en el periodo")
    activated_in_period: int = Field(..., description="Usuarios activados en el periodo")
    deleted_in_period: int = Field(..., description="Usuarios eliminados en el periodo")
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


@router.get("/users", response_model=UsersMetricsResponse)
async def get_users_in_period(
    from_date: Optional[str] = Query(None, alias="from", description="Fecha inicio (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, alias="to", description="Fecha fin (YYYY-MM-DD)"),
    page: int = Query(1, ge=1, description="Página"),
    page_size: int = Query(50, ge=1, le=100, description="Usuarios por página"),
    db: AsyncSession = Depends(get_db),
):
    """
    Obtiene lista paginada de usuarios creados en el periodo.
    
    Si no se especifican fechas, usa los últimos 30 días.
    Los emails se muestran parcialmente enmascarados por privacidad.
    """
    to_dt = _parse_date(to_date, "to", default_offset_days=0)
    from_dt = _parse_date(from_date, "from", default_offset_days=30) if from_date else (to_dt - timedelta(days=30))
    _validate_range(from_dt, to_dt)
    
    logger.info("users_in_period_request from=%s to=%s page=%d", from_dt, to_dt, page)
    
    try:
        agg = FunctionalAggregators(db)
        metrics = await agg.get_users_in_period(from_dt, to_dt, page, page_size)
        
        return UsersMetricsResponse(
            users=[UserListItem(
                user_id=u.user_id,
                email_masked=u.email_masked,
                full_name=u.full_name,
                status=u.status,
                is_activated=u.is_activated,
                created_at=u.created_at,
                activated_at=u.activated_at,
                last_login_at=u.last_login_at,
            ) for u in metrics.users],
            total=metrics.total,
            page=metrics.page,
            page_size=metrics.page_size,
            created_in_period=metrics.created_in_period,
            activated_in_period=metrics.activated_in_period,
            deleted_in_period=metrics.deleted_in_period,
            from_date=metrics.from_date,
            to_date=metrics.to_date,
            generated_at=metrics.generated_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("users_in_period_request failed: %s", e)
        raise HTTPException(status_code=500, detail="Error al obtener usuarios")


# Fin del archivo
