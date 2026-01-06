# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/schemas/operational_deliverability_schemas.py

Schemas Pydantic para métricas operativas de entregabilidad de correos.

Autor: Sistema
Fecha: 2026-01-05
"""
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


class DeliverabilityThresholds(BaseModel):
    """Umbrales de entregabilidad (fuente de verdad del backend)."""
    delivery_rate_warn: float
    delivery_rate_high: float
    bounce_rate_warn: float
    bounce_rate_high: float
    complaint_rate_warn: float
    complaint_rate_high: float
    users_multiple_bounces_warn: int
    users_multiple_bounces_high: int


class DeliverabilityAlert(BaseModel):
    """Alerta de entregabilidad."""
    code: str = Field(..., description="Código estable de la alerta")
    title: str = Field(..., description="Título para usuarios no técnicos")
    severity: Literal["low", "medium", "high"] = Field(..., description="Severidad")
    metric: str = Field(..., description="Nombre de la métrica")
    value: Union[int, float] = Field(..., description="Valor actual")
    threshold: str = Field(..., description="Umbral como texto")
    time_scope: Literal["periodo", "stock", "tiempo_real"] = Field(..., description="Alcance temporal")
    recommended_action: str = Field(..., description="Qué hacer (lenguaje no técnico)")
    details: Optional[str] = Field(None, description="Detalles adicionales")


class DeliverabilityOperationalResponse(BaseModel):
    """Respuesta de métricas operativas de entregabilidad."""
    
    # Conteos periodo
    emails_sent: int = Field(..., description="Correos enviados")
    emails_delivered: int = Field(..., description="Correos entregados")
    emails_bounced: int = Field(..., description="Correos rebotados")
    emails_failed: int = Field(..., description="Correos fallidos")
    emails_complained: int = Field(..., description="Quejas de spam")
    
    # Tasas
    delivery_rate: Optional[float] = Field(None, description="Tasa de entrega (delivered/sent)")
    bounce_rate: Optional[float] = Field(None, description="Tasa de rebote (bounced/sent)")
    complaint_rate: Optional[float] = Field(None, description="Tasa de quejas (complained/sent)")
    
    # Calidad
    users_with_multiple_bounces: int = Field(..., description="Usuarios con múltiples rebotes")
    
    # Alertas
    alerts: List[DeliverabilityAlert] = Field(default_factory=list)
    alerts_high: int = Field(0)
    alerts_medium: int = Field(0)
    alerts_low: int = Field(0)
    
    # Metadata
    from_date: str
    to_date: str
    generated_at: str
    notes: List[str] = Field(default_factory=list)
    thresholds: DeliverabilityThresholds
    
    # Trazabilidad
    email_events_source: str = Field("none", description="instrumented | fallback | none")
    email_events_partial: bool = Field(False, description="True si source=='fallback'")


# Fin del archivo
