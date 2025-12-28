
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/schemas/metrics_schemas.py

Esquemas Pydantic para métricas del módulo Auth.

Define estructuras de salida limpias (sin PII) para
exponer snapshots de métricas al panel administrativo.

Autor: Ixchel Beristain
Fecha: 2025-11-07
Actualizado: 2025-12-28 - Auth Metrics Cards v2
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class AuthMetricsSnapshot(BaseModel):
    """
    Snapshot de métricas del módulo Auth v2.
    
    Naming convention (snake_case):
    - users_*: métricas de usuarios
    - auth_*: métricas de autenticación/sesiones
    - payments_*: métricas de pagos
    """
    # ─────────────────────────────────────────────────────────────
    # Usuarios
    # ─────────────────────────────────────────────────────────────
    users_total: Optional[int] = Field(
        None, 
        description="Total histórico de usuarios registrados (incluye eliminados)"
    )
    users_deleted_total: Optional[int] = Field(
        None, 
        description="Usuarios eliminados (soft delete, deleted_at NOT NULL)"
    )
    users_suspended_total: Optional[int] = Field(
        None, 
        description="Usuarios suspendidos (vigentes, no eliminados)"
    )
    users_current_total: Optional[int] = Field(
        None, 
        description="Usuarios vigentes = total - eliminados - suspendidos"
    )
    users_activated_total: Optional[int] = Field(
        None, 
        description="Usuarios con cuenta activada"
    )
    
    # ─────────────────────────────────────────────────────────────
    # Sesiones (multi-sesión: usuarios pueden tener varios dispositivos)
    # ─────────────────────────────────────────────────────────────
    auth_active_sessions_total: Optional[int] = Field(
        None, 
        description="Total de sesiones activas (no revocadas, no expiradas)"
    )
    auth_active_users_total: Optional[int] = Field(
        None, 
        description="Usuarios únicos con al menos 1 sesión activa"
    )
    auth_sessions_per_user_avg: Optional[float] = Field(
        None, 
        description="Promedio de sesiones por usuario (sesiones / usuarios)"
    )
    
    # ─────────────────────────────────────────────────────────────
    # Conversión
    # ─────────────────────────────────────────────────────────────
    auth_activation_conversion_ratio: Optional[float] = Field(
        None, 
        description="Ratio de activación (0-1): activated / total"
    )
    payments_conversion_ratio: Optional[float] = Field(
        None, 
        description="Ratio de pago (0-1): paying_users / activated"
    )
    
    # ─────────────────────────────────────────────────────────────
    # Pagos
    # ─────────────────────────────────────────────────────────────
    payments_paying_users_total: Optional[int] = Field(
        None, 
        description="Usuarios con al menos 1 pago exitoso"
    )
    
    # ─────────────────────────────────────────────────────────────
    # Meta
    # ─────────────────────────────────────────────────────────────
    partial: bool = Field(
        False, 
        description="True si alguna métrica falló"
    )
    generated_at: Optional[str] = Field(
        None, 
        description="ISO timestamp de generación"
    )
    
    # ─────────────────────────────────────────────────────────────
    # Legacy aliases (deprecated, mantener temporalmente)
    # ─────────────────────────────────────────────────────────────
    active_sessions: Optional[int] = Field(
        None, 
        description="DEPRECATED: usar auth_active_sessions_total"
    )
    activation_conversion_ratio: Optional[float] = Field(
        None, 
        description="DEPRECATED: usar auth_activation_conversion_ratio"
    )


# Fin del archivo backend/app/modules/auth/metrics/schemas/metrics_schemas.py
