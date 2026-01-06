# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/schemas/operational_errors_schemas.py

Esquemas Pydantic para el dashboard operativo de Errores.

Autor: Sistema
Fecha: 2026-01-06
"""
from typing import List, Optional, Union
from pydantic import BaseModel, Field


class ErrorsThresholds(BaseModel):
    """Umbrales para alertas de errores (fuente de verdad).
    
    REGLA DE SEVERIDAD ÚNICA:
      - valor >= umbral_high ⇒ HIGH
      - valor >= umbral_warn ⇒ MEDIUM
      - valor > 0 (informativo) ⇒ LOW (solo si no hay warn/high)
    """
    login_failures_warn: int = Field(10, description="Fallos de login >= warn → MEDIUM")
    login_failures_high: int = Field(50, description="Fallos de login >= high → HIGH")
    
    login_failure_rate_warn: float = Field(0.15, description="Tasa de fallo >= 15% → MEDIUM")
    login_failure_rate_high: float = Field(0.35, description="Tasa de fallo >= 35% → HIGH")
    
    rate_limits_warn: int = Field(3, description="Rate limits >= warn → MEDIUM")
    rate_limits_high: int = Field(15, description="Rate limits >= high → HIGH")
    
    lockouts_warn: int = Field(2, description="Lockouts >= warn → MEDIUM")
    lockouts_high: int = Field(10, description="Lockouts >= high → HIGH")
    
    http_5xx_warn: int = Field(5, description="HTTP 5xx >= warn → MEDIUM")
    http_5xx_high: int = Field(20, description="HTTP 5xx >= high → HIGH")
    
    http_4xx_warn: int = Field(20, description="HTTP 4xx >= warn → MEDIUM")
    http_4xx_high: int = Field(100, description="HTTP 4xx >= high → HIGH")
    
    failed_reasons_concentration_warn: float = Field(0.50, description="Concentración en una razón >= 50% → MEDIUM")
    failed_reasons_concentration_high: float = Field(0.80, description="Concentración >= 80% → HIGH")


from typing import Literal

AlertSeverity = Literal["low", "medium", "high"]


class ErrorsAlert(BaseModel):
    """Una alerta del dashboard de errores."""
    code: str = Field(..., description="Código estable, ej. HIGH_LOGIN_FAILURES")
    title: str = Field(..., description="Título legible para administrador")
    severity: AlertSeverity = Field(..., description="low, medium, high")
    metric: str = Field(..., description="Nombre de la métrica relacionada")
    value: Union[int, float] = Field(..., description="Valor actual (int para conteos, float para ratios)")
    threshold: str = Field(..., description="Umbral descriptivo ej. '>= 50 fallos'")
    time_scope: str = Field(..., description="periodo, stock, tiempo_real")
    recommended_action: str = Field(..., description="Acción sugerida para NO técnicos")
    details: Optional[str] = Field(None, description="Detalles adicionales")


class LoginFailureByReasonItem(BaseModel):
    """Desglose de fallos por razón."""
    reason: str = Field(..., description="Razón del fallo")
    count: int = Field(0, description="Cantidad de fallos")
    percentage: Optional[float] = Field(None, description="Porcentaje del total (0-1)")


class ErrorsDailySeries(BaseModel):
    """Serie diaria para gráfico."""
    date: str = Field(..., description="Fecha YYYY-MM-DD")
    login_failures: int = 0
    rate_limits: int = 0
    lockouts: int = 0


class ErrorsOperationalResponse(BaseModel):
    """Response for GET /_internal/auth/metrics/operational/errors (mejorado)."""
    
    # ─────────────────────────────────────────────────────────────────
    # MÉTRICAS PERIODO
    # ─────────────────────────────────────────────────────────────────
    login_failures_total: int = Field(0, description="Fallos de login en periodo")
    login_failures_by_reason: List[LoginFailureByReasonItem] = Field(
        default_factory=list, 
        description="Top razones de fallo"
    )
    login_failure_rate: Optional[float] = Field(
        None, 
        description="Tasa de fallo (0-1), null si no hay intentos"
    )
    
    rate_limit_triggers: int = Field(0, description="Rate limits activados")
    lockouts_total: int = Field(0, description="Bloqueos por exceso de intentos")
    
    # Activation y password reset failures (si están instrumentados)
    activation_failures: int = Field(0, description="Fallos de activación (si instrumentado)")
    password_reset_failures: int = Field(0, description="Fallos de password reset (si instrumentado)")
    
    # HTTP errors (probablemente no instrumentados)
    http_4xx_count: int = Field(0, description="Errores HTTP 4xx")
    http_5xx_count: int = Field(0, description="Errores HTTP 5xx")
    
    # ─────────────────────────────────────────────────────────────────
    # SERIES (para gráfico)
    # ─────────────────────────────────────────────────────────────────
    daily_series: List[ErrorsDailySeries] = Field(
        default_factory=list,
        description="Serie diaria de errores"
    )
    
    # ─────────────────────────────────────────────────────────────────
    # ALERTAS
    # ─────────────────────────────────────────────────────────────────
    alerts: List[ErrorsAlert] = Field(default_factory=list, description="Alertas activas")
    alerts_high: int = Field(0, description="Conteo de alertas HIGH")
    alerts_medium: int = Field(0, description="Conteo de alertas MEDIUM")
    alerts_low: int = Field(0, description="Conteo de alertas LOW")
    
    # ─────────────────────────────────────────────────────────────────
    # THRESHOLDS (fuente de verdad)
    # ─────────────────────────────────────────────────────────────────
    thresholds: ErrorsThresholds = Field(
        default_factory=ErrorsThresholds,
        description="Umbrales usados para alertas"
    )
    
    # ─────────────────────────────────────────────────────────────────
    # METADATA
    # ─────────────────────────────────────────────────────────────────
    from_date: str = Field(..., description="Inicio del periodo YYYY-MM-DD")
    to_date: str = Field(..., description="Fin del periodo YYYY-MM-DD")
    generated_at: str = Field(..., description="Timestamp de generación ISO")
    notes: List[str] = Field(default_factory=list, description="Notas operativas")
    
    # ─────────────────────────────────────────────────────────────────
    # PARCIALIDAD
    # ─────────────────────────────────────────────────────────────────
    errors_partial: bool = Field(
        False, 
        description="True si alguna sección secundaria no está instrumentada (HTTP, activation, password_reset)"
    )
    has_partial_sections: bool = Field(
        False,
        description="Alias semántico: True si hay secciones con datos incompletos"
    )
    partial_sections: List[str] = Field(
        default_factory=list,
        description="Lista de secciones incompletas: ['http', 'activation_failures', 'password_reset_failures']"
    )
    http_instrumented: bool = Field(
        False, 
        description="True si HTTP errors están instrumentados"
    )
    activation_failures_instrumented: bool = Field(
        False,
        description="True si fallos de activación están instrumentados"
    )
    password_reset_failures_instrumented: bool = Field(
        False,
        description="True si fallos de password reset están instrumentados"
    )


# Fin del archivo
