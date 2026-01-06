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


class SecurityThresholds(BaseModel):
    """Todos los umbrales usados para cálculos de seguridad. Fuente de verdad.
    
    REGLA DE SEVERIDAD ÚNICA:
      - valor >= umbral_high ⇒ HIGH
      - valor >= umbral_warn ⇒ MEDIUM
      - valor > 0 (informativo) ⇒ LOW
    """
    high_failures: int = Field(5, description="Umbral de fallos para detectar IPs/usuarios sospechosos")
    multiple_sessions: int = Field(1, description="Umbral de sesiones múltiples por usuario")
    multiple_reset_requests: int = Field(1, description="Umbral de solicitudes de reset por usuario")
    login_failure_rate_warn: float = Field(0.10, description="Umbral warning para tasa de fallo → MEDIUM")
    login_failure_rate_high: float = Field(0.30, description="Umbral crítico para tasa de fallo → HIGH")
    ips_with_high_failures_warn: int = Field(1, description="Umbral warning para IPs sospechosas → MEDIUM")
    ips_with_high_failures_high: int = Field(10, description="Umbral crítico para IPs sospechosas → HIGH")
    users_with_high_failures_warn: int = Field(1, description="Umbral warning para usuarios sospechosos → MEDIUM")
    users_with_high_failures_high: int = Field(10, description="Umbral crítico para usuarios sospechosos → HIGH")
    lockouts_triggered_warn: int = Field(1, description="Umbral warning para bloqueos → MEDIUM")
    lockouts_triggered_high: int = Field(5, description="Umbral crítico para bloqueos → HIGH")
    reset_requests_by_user_warn: int = Field(1, description="Umbral warning para resets múltiples → MEDIUM")
    reset_requests_by_user_high: int = Field(5, description="Umbral crítico para resets múltiples → HIGH")
    users_with_multiple_sessions_warn: int = Field(2, description="Umbral warning para sesiones múltiples → MEDIUM")
    users_with_multiple_sessions_high: int = Field(10, description="Umbral crítico para sesiones múltiples → HIGH")
    sessions_expiring_warn: int = Field(10, description="Umbral para sesiones por expirar → LOW")
    accounts_locked_warn: int = Field(1, description="Umbral para cuentas bloqueadas → MEDIUM")
    login_no_session_warn: int = Field(3, description="Umbral warning para logins sin sesión → MEDIUM")
    login_no_session_high: int = Field(10, description="Umbral crítico para logins sin sesión → HIGH")


from typing import Union

class SecurityAlert(BaseModel):
    """Una alerta de seguridad."""
    code: str = Field(..., description="Código estable, ej. HIGH_LOGIN_FAILURE_RATE")
    title: str = Field(..., description="Título legible")
    severity: str = Field(..., description="low, medium, high")
    metric: str = Field(..., description="Nombre de la métrica")
    value: Union[int, float] = Field(..., description="Valor actual (int para conteos, float para ratios)")
    threshold: str = Field(..., description="Umbral descriptivo")
    time_scope: str = Field(..., description="periodo, stock, tiempo_real")
    recommended_action: str = Field(..., description="Acción recomendada")
    details: Optional[str] = Field(None, description="Detalles adicionales")


class SecurityMetricsResponse(BaseModel):
    """Response for GET /_internal/auth/metrics/operational/security"""
    
    # 1. Accesos (periodo)
    login_attempts_total: int = Field(0, description="Total de intentos de login")
    login_attempts_failed: int = Field(0, description="Intentos fallidos")
    login_attempts_success: int = Field(0, description="Intentos exitosos")
    login_failure_rate: Optional[float] = Field(None, description="Tasa de fallo (0-1)")
    
    # 2. Señales de fuerza bruta
    ips_with_high_failures: int = Field(0, description="IPs con más fallos que el umbral")
    users_with_high_failures: int = Field(0, description="Usuarios con más fallos que el umbral")
    lockouts_triggered: int = Field(0, description="Bloqueos activados en el periodo")
    accounts_locked_active: int = Field(0, description="Cuentas bloqueadas actualmente (stock)")
    
    # 3. Sesiones
    sessions_active: int = Field(0, description="Sesiones activas ahora")
    users_with_multiple_sessions: int = Field(0, description="Usuarios con múltiples sesiones")
    sessions_last_24h: int = Field(0, description="Sesiones creadas en últimas 24h")
    sessions_expiring_24h: int = Field(0, description="Sesiones que expiran en próximas 24h")
    
    # 4. Password reset (periodo)
    password_reset_requests: int = Field(0, description="Solicitudes de reset")
    password_reset_completed: int = Field(0, description="Resets completados")
    password_reset_abandoned: int = Field(0, description="Resets abandonados (expirados sin usar)")
    reset_requests_by_user_gt_1: int = Field(0, description="Usuarios con múltiples solicitudes")
    
    # 5. Indicadores de riesgo
    users_with_failed_login_and_reset: int = Field(0, description="Usuarios con fallo + reset")
    accounts_with_login_but_no_recent_session: int = Field(0, description="Login exitoso pero sin sesión")
    
    # 6. Alertas
    alerts: List[SecurityAlert] = Field(default_factory=list, description="Lista de alertas activas")
    alerts_high: int = Field(0, description="Conteo de alertas HIGH")
    alerts_medium: int = Field(0, description="Conteo de alertas MEDIUM")
    alerts_low: int = Field(0, description="Conteo de alertas LOW")
    
    # Metadata
    from_date: str = Field(..., description="Inicio del periodo")
    to_date: str = Field(..., description="Fin del periodo")
    generated_at: str = Field(..., description="Timestamp de generación")
    notes: List[str] = Field(default_factory=list, description="Notas operativas")
    thresholds: SecurityThresholds = Field(default_factory=SecurityThresholds, description="Umbrales usados")


# Fin del archivo
