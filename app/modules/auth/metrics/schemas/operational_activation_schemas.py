# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/schemas/operational_activation_schemas.py

Schemas Pydantic para métricas operativas de activación.

Autor: Sistema
Fecha: 2026-01-05
"""
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


class ActivationThresholds(BaseModel):
    """Umbrales de activación (fuente de verdad del backend)."""
    activation_expirations_warn: int
    activation_expirations_high: int
    activation_failure_rate_warn: float
    activation_failure_rate_high: float
    slow_activation_warn: int
    slow_activation_high: int
    multiple_resends_warn: int
    multiple_resends_high: int
    pending_activations_warn: int
    pending_activations_high: int


class ActivationAlert(BaseModel):
    """Alerta de activación."""
    code: str = Field(..., description="Código estable de la alerta")
    title: str = Field(..., description="Título para usuarios no técnicos")
    severity: Literal["low", "medium", "high"] = Field(..., description="Severidad")
    metric: str = Field(..., description="Nombre de la métrica")
    value: Union[int, float] = Field(..., description="Valor actual")
    threshold: str = Field(..., description="Umbral como texto")
    time_scope: Literal["periodo", "stock", "tiempo_real"] = Field(..., description="Alcance temporal")
    recommended_action: str = Field(..., description="Qué hacer (lenguaje no técnico)")
    details: Optional[str] = Field(None, description="Detalles adicionales")


class ActivationOperationalResponse(BaseModel):
    """Respuesta de métricas operativas de activación."""
    
    # Periodo
    activation_emails_sent: int = Field(..., description="Emails de activación enviados")
    activations_completed: int = Field(..., description="Activaciones completadas")
    activation_tokens_expired: int = Field(..., description="Tokens expirados en periodo")
    activation_resends: int = Field(..., description="Reenvíos de email")
    avg_time_to_activate_seconds: Optional[float] = Field(None, description="Tiempo promedio de activación (segundos)")
    
    # Calidad / Pendientes
    pending_tokens_stock_24h: int = Field(0, description="Tokens vigentes, creados >24h, sin consumir (stock)")
    pending_created_in_period_24h: int = Field(0, description="Tokens creados en periodo que pasaron 24h sin activar")
    users_with_multiple_resends: int = Field(..., description="Usuarios con múltiples reenvíos")
    
    # Stock
    activation_tokens_active: int = Field(..., description="Tokens válidos ahora")
    activation_tokens_expired_stock: int = Field(..., description="Tokens expirados (histórico)")
    
    # Tasa
    activation_failure_rate: Optional[float] = Field(None, description="Tasa de fallo (1 - completed/sent)")
    
    # Alertas
    alerts: List[ActivationAlert] = Field(default_factory=list)
    alerts_high: int = Field(0)
    alerts_medium: int = Field(0)
    alerts_low: int = Field(0)
    
    # Metadata
    from_date: str
    to_date: str
    generated_at: str
    notes: List[str] = Field(default_factory=list)
    thresholds: ActivationThresholds
    
    # Trazabilidad
    email_events_source: str = Field("none", description="instrumented | fallback | none")
    email_events_partial: bool = Field(False, description="True si source=='fallback'")
    resends_instrumented: bool = Field(False, description="True si reenvíos están instrumentados")


# Fin del archivo
