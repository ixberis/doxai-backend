# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/routes/alert_routes.py

Rutas admin para gestión de alertas de seguridad (ACK/SNOOZE).

Todas las rutas requieren require_admin_strict.
Transacciones atómicas: commit/rollback en la ruta.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.dependencies import require_admin_strict
from app.modules.auth.services.token_service import get_current_user_id
from app.shared.database.database import get_db

from ..schemas.alert_state_schemas import (
    AlertStatus, AlertAction,
    AlertAckRequest, AlertSnoozeRequest,
    AlertUnsnozeRequest, AlertReopenRequest,
    AlertStateRead, AlertEventRead,
    AlertStatesListResponse, AlertEventsListResponse,
    AlertActionResponse,
)
from ..services.alert_state_service import AlertStateService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/_internal/auth/alerts",
    tags=["auth-alerts-admin"],
    dependencies=[Depends(require_admin_strict)],
)


def _get_client_info(request: Request) -> tuple[Optional[str], Optional[str]]:
    """Extrae IP y User-Agent del request."""
    ip = request.client.host if request.client else None
    ua = request.headers.get("User-Agent")
    return ip, ua


# ─────────────────────────────────────────────────────────────────
# ACTIONS (con commit/rollback atómico)
# ─────────────────────────────────────────────────────────────────

@router.post("/{alert_key}/ack", response_model=AlertActionResponse)
async def acknowledge_alert(
    alert_key: str,
    body: AlertAckRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_user_id: str = Depends(get_current_user_id),
):
    """
    Reconoce una alerta.
    
    El estado cambia a 'acknowledged' y se registra quién/cuándo.
    """
    actor_id = UUID(auth_user_id)
    ip, ua = _get_client_info(request)
    
    service = AlertStateService(db)
    
    try:
        await service.acknowledge(
            alert_key=alert_key,
            actor_auth_user_id=actor_id,
            actor_ip=ip,
            actor_user_agent=ua,
            comment=body.comment,
            scope_from=body.scope_from,
            scope_to=body.scope_to,
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.exception("Error acknowledging alert %s: %s", alert_key, e)
        raise HTTPException(status_code=500, detail="Error al reconocer alerta")
    
    return AlertActionResponse(
        success=True,
        alert_key=alert_key,
        action=AlertAction.ACK,
        new_status=AlertStatus.ACKNOWLEDGED,
        message=f"Alerta {alert_key} reconocida",
    )


@router.post("/{alert_key}/snooze", response_model=AlertActionResponse)
async def snooze_alert(
    alert_key: str,
    body: AlertSnoozeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_user_id: str = Depends(get_current_user_id),
):
    """
    Silencia una alerta por un periodo.
    
    Puedes especificar:
    - duration_seconds: duración en segundos
    - snoozed_until: fecha/hora específica
    
    Si no se especifica ninguno, default = 24 horas.
    """
    actor_id = UUID(auth_user_id)
    ip, ua = _get_client_info(request)
    
    service = AlertStateService(db)
    
    try:
        new_state = await service.snooze(
            alert_key=alert_key,
            actor_auth_user_id=actor_id,
            duration_seconds=body.duration_seconds,
            snoozed_until=body.snoozed_until,
            actor_ip=ip,
            actor_user_agent=ua,
            comment=body.comment,
            scope_from=body.scope_from,
            scope_to=body.scope_to,
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.exception("Error snoozing alert %s: %s", alert_key, e)
        raise HTTPException(status_code=500, detail="Error al silenciar alerta")
    
    until = new_state.get("snoozed_until")
    until_str = until.isoformat() if until else "desconocido"
    
    return AlertActionResponse(
        success=True,
        alert_key=alert_key,
        action=AlertAction.SNOOZE,
        new_status=AlertStatus.SNOOZED,
        message=f"Alerta {alert_key} silenciada hasta {until_str}",
    )


@router.post("/{alert_key}/unsnooze", response_model=AlertActionResponse)
async def unsnooze_alert(
    alert_key: str,
    body: AlertUnsnozeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_user_id: str = Depends(get_current_user_id),
):
    """Quita el silenciamiento de una alerta."""
    actor_id = UUID(auth_user_id)
    ip, ua = _get_client_info(request)
    
    service = AlertStateService(db)
    
    try:
        await service.unsnooze(
            alert_key=alert_key,
            actor_auth_user_id=actor_id,
            actor_ip=ip,
            actor_user_agent=ua,
            scope_from=body.scope_from,
            scope_to=body.scope_to,
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.exception("Error unsnoozing alert %s: %s", alert_key, e)
        raise HTTPException(status_code=500, detail="Error al reactivar alerta")
    
    return AlertActionResponse(
        success=True,
        alert_key=alert_key,
        action=AlertAction.UNSNOOZE,
        new_status=AlertStatus.OPEN,
        message=f"Alerta {alert_key} reactivada",
    )


@router.post("/{alert_key}/reopen", response_model=AlertActionResponse)
async def reopen_alert(
    alert_key: str,
    body: AlertReopenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_user_id: str = Depends(get_current_user_id),
):
    """Reabre una alerta (quita ACK o SNOOZE)."""
    actor_id = UUID(auth_user_id)
    ip, ua = _get_client_info(request)
    
    service = AlertStateService(db)
    
    try:
        await service.reopen(
            alert_key=alert_key,
            actor_auth_user_id=actor_id,
            actor_ip=ip,
            actor_user_agent=ua,
            scope_from=body.scope_from,
            scope_to=body.scope_to,
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.exception("Error reopening alert %s: %s", alert_key, e)
        raise HTTPException(status_code=500, detail="Error al reabrir alerta")
    
    return AlertActionResponse(
        success=True,
        alert_key=alert_key,
        action=AlertAction.REOPEN,
        new_status=AlertStatus.OPEN,
        message=f"Alerta {alert_key} reabierta",
    )


# ─────────────────────────────────────────────────────────────────
# QUERIES (solo lectura, no requieren commit)
# ─────────────────────────────────────────────────────────────────

@router.get("/states", response_model=AlertStatesListResponse)
async def get_alert_states(
    dashboard: str = "operational_security",
    scope_from: Optional[date] = None,
    scope_to: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    """Lista estados de alertas para un dashboard/periodo."""
    service = AlertStateService(db)
    states = await service.get_states(
        scope_from=scope_from,
        scope_to=scope_to,
    )
    
    return AlertStatesListResponse(
        states=[AlertStateRead(**s) for s in states],
        total=len(states),
    )


@router.get("/events", response_model=AlertEventsListResponse)
async def get_alert_events(
    alert_key: Optional[str] = None,
    scope_from: Optional[date] = None,
    scope_to: Optional[date] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """Lista eventos de auditoría de alertas."""
    service = AlertStateService(db)
    events = await service.get_events(
        alert_key=alert_key,
        scope_from=scope_from,
        scope_to=scope_to,
        limit=limit,
    )
    
    return AlertEventsListResponse(
        events=[AlertEventRead(**e) for e in events],
        total=len(events),
    )
