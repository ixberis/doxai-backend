# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/schemas/operational_schemas.py

Esquemas Pydantic para endpoints operativos de Auth.

Autor: Sistema
Fecha: 2026-01-03
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class OperationalSummaryResponse(BaseModel):
    """Response for GET /_internal/auth/metrics/operational/summary"""
    
    # Sessions (real-time)
    sessions_active_total: int = Field(0, description="Sesiones activas ahora")
    sessions_active_users: int = Field(0, description="Usuarios únicos con sesión")
    sessions_per_user_avg: Optional[float] = Field(None, description="Promedio sesiones/usuario")
    
    # Login attempts (period)
    login_attempts_total: int = Field(0, description="Intentos de login en periodo")
    login_attempts_failed: int = Field(0, description="Intentos fallidos")
    login_failure_rate: Optional[float] = Field(None, description="Tasa de fallo (0-1)")
    
    # Rate limits / lockouts
    rate_limit_triggers: int = Field(0, description="Rate limits activados")
    lockouts_total: int = Field(0, description="Bloqueos por exceso de intentos")
    
    # Emails (period)
    emails_sent_total: int = Field(0, description="Correos enviados")
    emails_failed_total: int = Field(0, description="Correos fallidos")
    email_failure_rate: Optional[float] = Field(None, description="Tasa de error de correo (0-1)")
    
    # Period
    period_from: Optional[str] = Field(None, description="Inicio del periodo (YYYY-MM-DD)")
    period_to: Optional[str] = Field(None, description="Fin del periodo (YYYY-MM-DD)")
    
    # Meta
    generated_at: str = Field(..., description="Timestamp de generación ISO")


class TopUserSessionsItem(BaseModel):
    """User with session count."""
    user_id: str
    user_email: str
    session_count: int


class SessionsDetailResponse(BaseModel):
    """Response for GET /_internal/auth/metrics/operational/sessions"""
    
    # Real-time
    sessions_active_total: int = Field(0)
    sessions_active_users: int = Field(0)
    sessions_per_user_avg: Optional[float] = None
    
    # Period
    sessions_created: int = Field(0, description="Sesiones creadas en periodo")
    sessions_expired: int = Field(0, description="Sesiones expiradas en periodo")
    sessions_revoked: int = Field(0, description="Sesiones revocadas en periodo")
    
    # Top users
    top_users: List[TopUserSessionsItem] = Field(default_factory=list)
    
    # Period
    period_from: Optional[str] = None
    period_to: Optional[str] = None
    
    # Meta
    generated_at: str


class LoginFailureByReasonItem(BaseModel):
    """Login failure count by reason."""
    reason: str
    count: int


class ErrorsDetailResponse(BaseModel):
    """Response for GET /_internal/auth/metrics/operational/errors"""
    
    # Login failures
    login_failures_by_reason: List[LoginFailureByReasonItem] = Field(default_factory=list)
    login_failures_total: int = Field(0)
    
    # Rate limits
    rate_limit_triggers: int = Field(0)
    rate_limit_by_ip: int = Field(0)
    rate_limit_by_user: int = Field(0)
    
    # Lockouts
    lockouts_total: int = Field(0)
    lockouts_by_ip: int = Field(0)
    lockouts_by_user: int = Field(0)
    
    # HTTP errors (not instrumented)
    http_4xx_count: int = Field(0, description="Errores 4xx (source=not_instrumented)")
    http_5xx_count: int = Field(0, description="Errores 5xx (source=not_instrumented)")
    
    # Period
    period_from: Optional[str] = None
    period_to: Optional[str] = None
    
    # Meta
    generated_at: str


# Fin del archivo
