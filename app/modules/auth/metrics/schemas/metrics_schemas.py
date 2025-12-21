
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/schemas/metrics_schemas.py

Esquemas Pydantic para métricas del módulo Auth.

Define estructuras de salida limpias (sin PII) para
exponer snapshots de métricas al panel administrativo.

Autor: Ixchel Beristain
Fecha: 2025-11-07
Actualizado: 2025-12-21 - Nombres definitivos de métricas
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class AuthMetricsSnapshot(BaseModel):
    """
    Snapshot de métricas del módulo Auth.
    
    Nombres definitivos (snake_case):
    - users_*: métricas de usuarios
    - auth_*: métricas de autenticación/sesiones
    - payments_*: métricas de pagos
    """
    # Usuarios
    users_total: Optional[int] = Field(None, description="Total de usuarios registrados")
    users_activated_total: Optional[int] = Field(None, description="Usuarios con cuenta activada")
    
    # Sesiones
    auth_active_sessions_total: Optional[int] = Field(None, description="Sesiones activas (no revocadas, no expiradas)")
    auth_active_users_total: Optional[int] = Field(None, description="Usuarios distintos con sesión activa")
    
    # Conversión
    auth_activation_conversion_ratio: Optional[float] = Field(None, description="Ratio activación (0-1)")
    
    # Pagos
    payments_paying_users_total: Optional[int] = Field(None, description="Usuarios con al menos 1 pago exitoso")
    
    # Meta
    partial: bool = Field(False, description="True si alguna métrica falló")
    generated_at: Optional[str] = Field(None, description="ISO timestamp de generación")
    
    # Legacy aliases (deprecated, mantener temporalmente)
    active_sessions: Optional[int] = Field(None, description="DEPRECATED: usar auth_active_sessions_total")
    activation_conversion_ratio: Optional[float] = Field(None, description="DEPRECATED: usar auth_activation_conversion_ratio")


# Fin del archivo backend/app/modules/auth/metrics/schemas/metrics_schemas.py
