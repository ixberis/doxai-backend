# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/services/alert_state_service.py

Servicio para gestión de estados de alertas (ACK/SNOOZE/REOPEN).

NOTA: NO hace commit. El caller (route) es responsable de commit/rollback.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.alert_state_repository import AlertStateRepository
from ..schemas.alert_state_schemas import (
    AlertStatus, AlertAction, AlertStateOverlay,
)

logger = logging.getLogger(__name__)


class AlertStateService:
    """Servicio para gestionar estados de alertas."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AlertStateRepository(db)
    
    # ─────────────────────────────────────────────────────────────
    # ACTIONS (todas en la misma transacción, NO commit)
    # ─────────────────────────────────────────────────────────────
    
    async def acknowledge(
        self,
        alert_key: str,
        actor_auth_user_id: UUID,
        actor_ip: Optional[str] = None,
        actor_user_agent: Optional[str] = None,
        comment: Optional[str] = None,
        scope_from: Optional[date] = None,
        scope_to: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Reconoce una alerta.
        
        Upsert state + insert event en la misma transacción.
        El caller debe hacer commit.
        """
        now = datetime.now(timezone.utc)
        
        # Obtener estado previo para audit
        prev_state = await self.repo.get_state(
            alert_key=alert_key,
            scope_from=scope_from,
            scope_to=scope_to,
        )
        prev_status = prev_state.get("status") if prev_state else "open"
        
        # Upsert estado
        new_state = await self.repo.upsert_state(
            alert_key=alert_key,
            status=AlertStatus.ACKNOWLEDGED,
            scope_from=scope_from,
            scope_to=scope_to,
            snoozed_until=None,
            acknowledged_at=now,
            acknowledged_by_auth_user_id=actor_auth_user_id,
            comment=comment,
        )
        
        # Registrar evento (misma transacción)
        await self.repo.insert_event(
            alert_key=alert_key,
            action=AlertAction.ACK,
            scope_from=scope_from,
            scope_to=scope_to,
            actor_auth_user_id=actor_auth_user_id,
            actor_ip=actor_ip,
            actor_user_agent=actor_user_agent,
            payload={
                "previous_status": prev_status,
                "comment": comment,
            },
        )
        
        logger.info(
            "Alert acknowledged: key=%s actor=%s",
            alert_key, actor_auth_user_id
        )
        
        return new_state
    
    async def snooze(
        self,
        alert_key: str,
        actor_auth_user_id: UUID,
        duration_seconds: Optional[int] = None,
        snoozed_until: Optional[datetime] = None,
        actor_ip: Optional[str] = None,
        actor_user_agent: Optional[str] = None,
        comment: Optional[str] = None,
        scope_from: Optional[date] = None,
        scope_to: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Silencia una alerta por un periodo.
        
        Upsert state + insert event en la misma transacción.
        El caller debe hacer commit.
        """
        now = datetime.now(timezone.utc)
        
        # Calcular snoozed_until
        if snoozed_until:
            until = snoozed_until
        elif duration_seconds:
            until = now + timedelta(seconds=duration_seconds)
        else:
            until = now + timedelta(hours=24)
        
        # Obtener estado previo
        prev_state = await self.repo.get_state(
            alert_key=alert_key,
            scope_from=scope_from,
            scope_to=scope_to,
        )
        prev_status = prev_state.get("status") if prev_state else "open"
        
        # Upsert estado
        new_state = await self.repo.upsert_state(
            alert_key=alert_key,
            status=AlertStatus.SNOOZED,
            scope_from=scope_from,
            scope_to=scope_to,
            snoozed_until=until,
            acknowledged_at=None,
            acknowledged_by_auth_user_id=actor_auth_user_id,
            comment=comment,
        )
        
        # Registrar evento
        await self.repo.insert_event(
            alert_key=alert_key,
            action=AlertAction.SNOOZE,
            scope_from=scope_from,
            scope_to=scope_to,
            actor_auth_user_id=actor_auth_user_id,
            actor_ip=actor_ip,
            actor_user_agent=actor_user_agent,
            payload={
                "previous_status": prev_status,
                "snoozed_until": until.isoformat(),
                "duration_seconds": duration_seconds,
                "comment": comment,
            },
        )
        
        logger.info(
            "Alert snoozed: key=%s until=%s actor=%s",
            alert_key, until, actor_auth_user_id
        )
        
        return new_state
    
    async def unsnooze(
        self,
        alert_key: str,
        actor_auth_user_id: UUID,
        actor_ip: Optional[str] = None,
        actor_user_agent: Optional[str] = None,
        scope_from: Optional[date] = None,
        scope_to: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Quita el silenciamiento de una alerta."""
        prev_state = await self.repo.get_state(
            alert_key=alert_key,
            scope_from=scope_from,
            scope_to=scope_to,
        )
        prev_snoozed_until = prev_state.get("snoozed_until") if prev_state else None
        
        new_state = await self.repo.upsert_state(
            alert_key=alert_key,
            status=AlertStatus.OPEN,
            scope_from=scope_from,
            scope_to=scope_to,
            snoozed_until=None,
            acknowledged_at=None,
            acknowledged_by_auth_user_id=None,
            comment=None,
        )
        
        await self.repo.insert_event(
            alert_key=alert_key,
            action=AlertAction.UNSNOOZE,
            scope_from=scope_from,
            scope_to=scope_to,
            actor_auth_user_id=actor_auth_user_id,
            actor_ip=actor_ip,
            actor_user_agent=actor_user_agent,
            payload={
                "previous_snoozed_until": prev_snoozed_until.isoformat() if prev_snoozed_until else None,
            },
        )
        
        logger.info("Alert unsnoozed: key=%s actor=%s", alert_key, actor_auth_user_id)
        
        return new_state
    
    async def reopen(
        self,
        alert_key: str,
        actor_auth_user_id: UUID,
        actor_ip: Optional[str] = None,
        actor_user_agent: Optional[str] = None,
        scope_from: Optional[date] = None,
        scope_to: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Reabre una alerta (quita ACK/SNOOZE)."""
        prev_state = await self.repo.get_state(
            alert_key=alert_key,
            scope_from=scope_from,
            scope_to=scope_to,
        )
        prev_status = prev_state.get("status") if prev_state else "open"
        
        new_state = await self.repo.upsert_state(
            alert_key=alert_key,
            status=AlertStatus.OPEN,
            scope_from=scope_from,
            scope_to=scope_to,
            snoozed_until=None,
            acknowledged_at=None,
            acknowledged_by_auth_user_id=None,
            comment=None,
        )
        
        await self.repo.insert_event(
            alert_key=alert_key,
            action=AlertAction.REOPEN,
            scope_from=scope_from,
            scope_to=scope_to,
            actor_auth_user_id=actor_auth_user_id,
            actor_ip=actor_ip,
            actor_user_agent=actor_user_agent,
            payload={"previous_status": prev_status},
        )
        
        logger.info("Alert reopened: key=%s actor=%s", alert_key, actor_auth_user_id)
        
        return new_state
    
    # ─────────────────────────────────────────────────────────────
    # OVERLAY: Aplicar estados a alertas computadas
    # ─────────────────────────────────────────────────────────────
    
    async def get_overlays_for_alerts(
        self,
        alert_keys: List[str],
        scope_from: Optional[date] = None,
        scope_to: Optional[date] = None,
    ) -> Dict[str, AlertStateOverlay]:
        """
        Obtiene overlays de estado para una lista de alert_keys.
        
        Returns:
            Dict[alert_key, AlertStateOverlay]
        """
        now = datetime.now(timezone.utc)
        overlays: Dict[str, AlertStateOverlay] = {}
        
        states = await self.repo.get_states_for_dashboard(
            scope_from=scope_from,
            scope_to=scope_to,
        )
        
        for state in states:
            key = state.get("alert_key")
            if key not in alert_keys:
                continue
            
            status_str = state.get("status", "open")
            status = AlertStatus(status_str)
            snoozed_until = state.get("snoozed_until")
            
            # Determinar si snooze está activo
            is_snoozed = (
                status == AlertStatus.SNOOZED and 
                snoozed_until and 
                snoozed_until > now
            )
            
            # Si snooze expiró, marcar como open
            if status == AlertStatus.SNOOZED and snoozed_until and snoozed_until <= now:
                status = AlertStatus.OPEN
                is_snoozed = False
            
            overlays[key] = AlertStateOverlay(
                status=status,
                is_snoozed=is_snoozed,
                is_acknowledged=(status == AlertStatus.ACKNOWLEDGED),
                snoozed_until=snoozed_until if is_snoozed else None,
                acknowledged_at=state.get("acknowledged_at"),
                acknowledged_by=state.get("acknowledged_by_auth_user_id"),
                comment=state.get("comment"),
            )
        
        # Alertas sin estado guardado = open por defecto
        for key in alert_keys:
            if key not in overlays:
                overlays[key] = AlertStateOverlay()
        
        return overlays
    
    # ─────────────────────────────────────────────────────────────
    # QUERIES (solo lectura)
    # ─────────────────────────────────────────────────────────────
    
    async def get_states(
        self,
        scope_from: Optional[date] = None,
        scope_to: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """
        Lista estados de alertas.
        
        Si un snooze expiró, devuelve status='open' en el response
        (sin modificar DB - higiene lazy).
        """
        now = datetime.now(timezone.utc)
        states = await self.repo.get_states_for_dashboard(
            scope_from=scope_from,
            scope_to=scope_to,
        )
        
        # Aplicar higiene: si snoozed_until <= now, devolver como open
        result = []
        for state in states:
            state_copy = dict(state)
            if (
                state_copy.get("status") == "snoozed" 
                and state_copy.get("snoozed_until")
                and state_copy["snoozed_until"] <= now
            ):
                state_copy["status"] = "open"
                state_copy["snoozed_until"] = None
                state_copy["_snooze_expired"] = True  # Flag informativo
            result.append(state_copy)
        
        return result
    
    async def get_events(
        self,
        alert_key: Optional[str] = None,
        scope_from: Optional[date] = None,
        scope_to: Optional[date] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Lista eventos de auditoría."""
        return await self.repo.get_events(
            alert_key=alert_key,
            scope_from=scope_from,
            scope_to=scope_to,
            limit=limit,
        )
