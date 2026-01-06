# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/schemas/operational_password_reset_schemas.py

Schemas Pydantic para métricas operativas de password reset.

Autor: Sistema
Fecha: 2026-01-06
"""
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


class PasswordResetThresholds(BaseModel):
    """Umbrales de password reset (fuente de verdad del backend)."""
    expirations_warn: int
    expirations_high: int
    failure_rate_warn: float
    failure_rate_high: float
    slow_reset_warn: int
    slow_reset_high: int
    multiple_requests_warn: int
    multiple_requests_high: int
    pending_24h_warn: int
    pending_24h_high: int


class PasswordResetAlert(BaseModel):
    """Alerta de password reset."""
    code: str = Field(..., description="Código estable de la alerta")
    title: str = Field(..., description="Título para usuarios no técnicos")
    severity: Literal["low", "medium", "high"] = Field(..., description="Severidad")
    metric: str = Field(..., description="Nombre de la métrica")
    value: Union[int, float] = Field(..., description="Valor actual")
    threshold: str = Field(..., description="Umbral como texto")
    time_scope: Literal["periodo", "stock", "tiempo_real"] = Field(..., description="Alcance temporal")
    recommended_action: str = Field(..., description="Qué hacer (lenguaje no técnico)")
    details: Optional[str] = Field(None, description="Detalles adicionales")


class PasswordResetOperationalResponse(BaseModel):
    """Respuesta de métricas operativas de password reset."""
    
    # Periodo
    password_reset_requests: int = Field(..., description="Solicitudes de reset en periodo")
    password_reset_emails_sent: int = Field(..., description="Emails de reset enviados")
    password_reset_completed: int = Field(..., description="Resets completados")
    password_reset_expired: int = Field(..., description="Tokens expirados sin uso")
    avg_time_to_reset_seconds: Optional[float] = Field(None, description="Tiempo promedio de reset (segundos)")
    
    # Calidad / Pendientes
    pending_tokens_stock_24h: int = Field(0, description="Tokens vigentes, creados >24h, sin usar (stock)")
    pending_created_in_period_24h: int = Field(0, description="Tokens creados en periodo que pasaron 24h sin usar")
    users_with_multiple_requests: int = Field(..., description="Usuarios con múltiples solicitudes")
    
    # Stock
    password_reset_tokens_active: int = Field(..., description="Tokens válidos ahora")
    password_reset_tokens_expired_stock: int = Field(..., description="Tokens expirados (histórico)")
    
    # Tasa
    password_reset_failure_rate: Optional[float] = Field(None, description="Tasa de fallo (1 - completed/sent)")
    
    # Alertas
    alerts: List[PasswordResetAlert] = Field(default_factory=list)
    alerts_high: int = Field(0)
    alerts_medium: int = Field(0)
    alerts_low: int = Field(0)
    
    # Metadata
    from_date: str
    to_date: str
    generated_at: str
    notes: List[str] = Field(default_factory=list)
    thresholds: PasswordResetThresholds
    
    # Trazabilidad
    email_events_source: str = Field("none", description="instrumented | fallback | none")
    email_events_partial: bool = Field(False, description="True si source=='fallback'")
    resends_instrumented: bool = Field(False, description="True si reenvíos están instrumentados")


# Fin del archivo
