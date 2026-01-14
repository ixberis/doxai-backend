# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/schemas/alert_state_schemas.py

Schemas Pydantic para gestión de estados de alertas (ACK/SNOOZE).
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AlertStatus(str, Enum):
    """Estados posibles de una alerta."""
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    SNOOZED = "snoozed"


class AlertAction(str, Enum):
    """Acciones sobre alertas."""
    ACK = "ack"
    SNOOZE = "snooze"
    UNSNOOZE = "unsnooze"
    REOPEN = "reopen"
    CLEAR_COMMENT = "clear_comment"


# ─────────────────────────────────────────────────────────────────
# Request schemas
# ─────────────────────────────────────────────────────────────────

class AlertAckRequest(BaseModel):
    """Request para reconocer una alerta."""
    comment: Optional[str] = Field(None, max_length=500)
    scope_from: Optional[date] = None
    scope_to: Optional[date] = None


class AlertSnoozeRequest(BaseModel):
    """Request para silenciar una alerta."""
    duration_seconds: Optional[int] = Field(
        None, 
        ge=60,  # Mínimo 1 minuto
        le=604800 * 4  # Máximo 28 días
    )
    snoozed_until: Optional[datetime] = None
    comment: Optional[str] = Field(None, max_length=500)
    scope_from: Optional[date] = None
    scope_to: Optional[date] = None


class AlertUnsnozeRequest(BaseModel):
    """Request para reactivar (quitar snooze) una alerta."""
    scope_from: Optional[date] = None
    scope_to: Optional[date] = None


class AlertReopenRequest(BaseModel):
    """Request para reabrir una alerta (quitar ACK)."""
    scope_from: Optional[date] = None
    scope_to: Optional[date] = None


# ─────────────────────────────────────────────────────────────────
# Response schemas
# ─────────────────────────────────────────────────────────────────

class AlertStateRead(BaseModel):
    """Estado de una alerta (lectura)."""
    id: int
    module: str
    dashboard: str
    alert_key: str
    scope_from: Optional[date] = None
    scope_to: Optional[date] = None
    status: AlertStatus
    snoozed_until: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by_auth_user_id: Optional[UUID] = None
    comment: Optional[str] = None
    updated_at: datetime

    class Config:
        from_attributes = True


class AlertEventRead(BaseModel):
    """Evento de auditoría de alerta (lectura)."""
    id: int
    module: str
    dashboard: str
    alert_key: str
    scope_from: Optional[date] = None
    scope_to: Optional[date] = None
    action: AlertAction
    actor_auth_user_id: Optional[UUID] = None
    actor_ip: Optional[str] = None
    actor_user_agent: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AlertStatesListResponse(BaseModel):
    """Lista de estados de alertas."""
    states: List[AlertStateRead]
    total: int


class AlertEventsListResponse(BaseModel):
    """Lista de eventos de alertas."""
    events: List[AlertEventRead]
    total: int


class AlertActionResponse(BaseModel):
    """Respuesta a una acción sobre alerta."""
    success: bool
    alert_key: str
    action: AlertAction
    new_status: AlertStatus
    message: str


# ─────────────────────────────────────────────────────────────────
# Overlay para alertas computadas
# ─────────────────────────────────────────────────────────────────

class AlertStateOverlay(BaseModel):
    """
    Overlay de estado para una alerta computada.
    Se anexa a cada SecurityAlert al aplicar estados.
    """
    status: AlertStatus = AlertStatus.OPEN
    is_snoozed: bool = False
    is_acknowledged: bool = False
    snoozed_until: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[UUID] = None
    comment: Optional[str] = None
