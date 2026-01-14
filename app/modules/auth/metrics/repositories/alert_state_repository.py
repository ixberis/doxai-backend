# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/repositories/alert_state_repository.py

Repositorio para operaciones CRUD sobre auth_alert_states y auth_alert_events.

NOTA: NO hace commit. El caller (route) es responsable de commit/rollback.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas.alert_state_schemas import AlertStatus, AlertAction

logger = logging.getLogger(__name__)


class AlertStateRepository:
    """Repositorio para estados y eventos de alertas."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # ─────────────────────────────────────────────────────────────
    # STATES: CRUD
    # ─────────────────────────────────────────────────────────────
    
    async def get_state(
        self,
        alert_key: str,
        module: str = "auth",
        dashboard: str = "operational_security",
        scope_from: Optional[date] = None,
        scope_to: Optional[date] = None,
    ) -> Optional[Dict[str, Any]]:
        """Obtiene el estado de una alerta específica."""
        q = text("""
            SELECT 
                id, module, dashboard, alert_key,
                scope_from, scope_to, status,
                snoozed_until, acknowledged_at, 
                acknowledged_by_auth_user_id, comment, updated_at
            FROM public.auth_alert_states
            WHERE module = :module
              AND dashboard = :dashboard
              AND alert_key = :alert_key
              AND (scope_from IS NOT DISTINCT FROM :scope_from)
              AND (scope_to IS NOT DISTINCT FROM :scope_to)
        """)
        result = await self.db.execute(q, {
            "module": module,
            "dashboard": dashboard,
            "alert_key": alert_key,
            "scope_from": scope_from,
            "scope_to": scope_to,
        })
        row = result.first()
        if not row:
            return None
        return dict(row._mapping)
    
    async def get_states_for_dashboard(
        self,
        module: str = "auth",
        dashboard: str = "operational_security",
        scope_from: Optional[date] = None,
        scope_to: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """Obtiene todos los estados para un dashboard/scope."""
        q = text("""
            SELECT 
                id, module, dashboard, alert_key,
                scope_from, scope_to, status,
                snoozed_until, acknowledged_at,
                acknowledged_by_auth_user_id, comment, updated_at
            FROM public.auth_alert_states
            WHERE module = :module
              AND dashboard = :dashboard
              AND (
                  (scope_from IS NULL AND scope_to IS NULL)
                  OR (scope_from = :scope_from AND scope_to = :scope_to)
              )
        """)
        result = await self.db.execute(q, {
            "module": module,
            "dashboard": dashboard,
            "scope_from": scope_from,
            "scope_to": scope_to,
        })
        return [dict(row._mapping) for row in result.fetchall()]
    
    async def upsert_state(
        self,
        alert_key: str,
        status: AlertStatus,
        module: str = "auth",
        dashboard: str = "operational_security",
        scope_from: Optional[date] = None,
        scope_to: Optional[date] = None,
        snoozed_until: Optional[datetime] = None,
        acknowledged_at: Optional[datetime] = None,
        acknowledged_by_auth_user_id: Optional[UUID] = None,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Inserta o actualiza el estado de una alerta.
        
        Usa índices parciales únicos para manejar NULL scopes:
        - ux_auth_alert_states_scope_null: (module,dashboard,alert_key) WHERE scope IS NULL
        - ux_auth_alert_states_scope_dates: (...,scope_from,scope_to) WHERE scope NOT NULL
        
        ON CONFLICT especifica las columnas del índice único parcial.
        PostgreSQL matcheará el índice correcto automáticamente.
        
        NOTA: NO hace commit. El caller es responsable.
        """
        # Elegir ON CONFLICT según si scope es NULL o no
        if scope_from is None and scope_to is None:
            # Matchea con ux_auth_alert_states_scope_null
            q = text("""
                INSERT INTO public.auth_alert_states (
                    module, dashboard, alert_key, scope_from, scope_to,
                    status, snoozed_until, acknowledged_at,
                    acknowledged_by_auth_user_id, comment, updated_at
                ) VALUES (
                    :module, :dashboard, :alert_key, NULL, NULL,
                    :status, :snoozed_until, :acknowledged_at,
                    :acknowledged_by_auth_user_id, :comment, now()
                )
                ON CONFLICT (module, dashboard, alert_key)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    snoozed_until = EXCLUDED.snoozed_until,
                    acknowledged_at = EXCLUDED.acknowledged_at,
                    acknowledged_by_auth_user_id = EXCLUDED.acknowledged_by_auth_user_id,
                    comment = EXCLUDED.comment,
                    updated_at = now()
                RETURNING 
                    id, module, dashboard, alert_key, scope_from, scope_to,
                    status, snoozed_until, acknowledged_at,
                    acknowledged_by_auth_user_id, comment, updated_at
            """)
        else:
            # Matchea con ux_auth_alert_states_scope_dates
            q = text("""
                INSERT INTO public.auth_alert_states (
                    module, dashboard, alert_key, scope_from, scope_to,
                    status, snoozed_until, acknowledged_at,
                    acknowledged_by_auth_user_id, comment, updated_at
                ) VALUES (
                    :module, :dashboard, :alert_key, :scope_from, :scope_to,
                    :status, :snoozed_until, :acknowledged_at,
                    :acknowledged_by_auth_user_id, :comment, now()
                )
                ON CONFLICT (module, dashboard, alert_key, scope_from, scope_to)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    snoozed_until = EXCLUDED.snoozed_until,
                    acknowledged_at = EXCLUDED.acknowledged_at,
                    acknowledged_by_auth_user_id = EXCLUDED.acknowledged_by_auth_user_id,
                    comment = EXCLUDED.comment,
                    updated_at = now()
                RETURNING 
                    id, module, dashboard, alert_key, scope_from, scope_to,
                    status, snoozed_until, acknowledged_at,
                    acknowledged_by_auth_user_id, comment, updated_at
            """)
        
        result = await self.db.execute(q, {
            "module": module,
            "dashboard": dashboard,
            "alert_key": alert_key,
            "scope_from": scope_from,
            "scope_to": scope_to,
            "status": status.value,
            "snoozed_until": snoozed_until,
            "acknowledged_at": acknowledged_at,
            "acknowledged_by_auth_user_id": acknowledged_by_auth_user_id,
            "comment": comment,
        })
        row = result.first()
        # NO commit aquí
        return dict(row._mapping) if row else {}
    
    # ─────────────────────────────────────────────────────────────
    # EVENTS: INSERT + LIST
    # ─────────────────────────────────────────────────────────────
    
    async def insert_event(
        self,
        alert_key: str,
        action: AlertAction,
        module: str = "auth",
        dashboard: str = "operational_security",
        scope_from: Optional[date] = None,
        scope_to: Optional[date] = None,
        actor_auth_user_id: Optional[UUID] = None,
        actor_ip: Optional[str] = None,
        actor_user_agent: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Inserta un evento de auditoría.
        
        NOTA: NO hace commit. El caller es responsable.
        """
        q = text("""
            INSERT INTO public.auth_alert_events (
                module, dashboard, alert_key, scope_from, scope_to,
                action, actor_auth_user_id, actor_ip, actor_user_agent,
                payload, created_at
            ) VALUES (
                :module, :dashboard, :alert_key, :scope_from, :scope_to,
                :action, :actor_auth_user_id, :actor_ip, :actor_user_agent,
                :payload, now()
            )
            RETURNING id, created_at
        """)
        result = await self.db.execute(q, {
            "module": module,
            "dashboard": dashboard,
            "alert_key": alert_key,
            "scope_from": scope_from,
            "scope_to": scope_to,
            "action": action.value,
            "actor_auth_user_id": actor_auth_user_id,
            "actor_ip": actor_ip,
            "actor_user_agent": actor_user_agent,
            "payload": json.dumps(payload) if payload else None,
        })
        row = result.first()
        # NO commit aquí
        return dict(row._mapping) if row else {}
    
    async def get_events(
        self,
        alert_key: Optional[str] = None,
        module: str = "auth",
        dashboard: str = "operational_security",
        scope_from: Optional[date] = None,
        scope_to: Optional[date] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Lista eventos de auditoría."""
        conditions = ["module = :module", "dashboard = :dashboard"]
        params: Dict[str, Any] = {
            "module": module,
            "dashboard": dashboard,
            "limit": limit,
        }
        
        if alert_key:
            conditions.append("alert_key = :alert_key")
            params["alert_key"] = alert_key
        
        if scope_from:
            conditions.append("scope_from = :scope_from")
            params["scope_from"] = scope_from
        
        if scope_to:
            conditions.append("scope_to = :scope_to")
            params["scope_to"] = scope_to
        
        where_clause = " AND ".join(conditions)
        
        q = text(f"""
            SELECT 
                id, module, dashboard, alert_key, scope_from, scope_to,
                action, actor_auth_user_id, actor_ip, actor_user_agent,
                payload, created_at
            FROM public.auth_alert_events
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit
        """)
        
        result = await self.db.execute(q, params)
        return [dict(row._mapping) for row in result.fetchall()]
