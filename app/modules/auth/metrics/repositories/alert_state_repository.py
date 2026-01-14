# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/repositories/alert_state_repository.py

Repositorio para operaciones CRUD sobre auth_alert_states y auth_alert_events.

NOTA: NO hace commit. El caller (route) es responsable de commit/rollback.

ARQUITECTURA scope_key:
- scope_key es el arbiter canónico para upsert.
- Si scope_from/to son NULL => scope_key = 'global'
- Si scope_from/to tienen fechas => scope_key = 'YYYY-MM-DD_YYYY-MM-DD'
- ON CONFLICT siempre usa (module, dashboard, alert_key, scope_key)
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


def compute_scope_key(
    scope_from: Optional[date] = None,
    scope_to: Optional[date] = None,
    strict: bool = True,
) -> str:
    """
    Calcula el scope_key canónico para upsert.
    
    - Si scope_from y scope_to son NULL => 'global'
    - Si ambos tienen valor => 'YYYY-MM-DD_YYYY-MM-DD'
    - Si solo uno tiene valor:
      - strict=True (default): raise ValueError
      - strict=False: normaliza a 'YYYY-MM-DD_' o '_YYYY-MM-DD'
    
    Args:
        scope_from: Fecha inicio del scope (opcional)
        scope_to: Fecha fin del scope (opcional)
        strict: Si True, rechaza scopes parciales con ValueError
    
    Returns:
        scope_key canónico
    
    Raises:
        ValueError: Si strict=True y solo uno de scope_from/to está presente
    """
    if scope_from is None and scope_to is None:
        return "global"
    
    if scope_from is not None and scope_to is not None:
        return f"{scope_from.isoformat()}_{scope_to.isoformat()}"
    
    # Scope parcial (solo from o solo to)
    if strict:
        raise ValueError(
            f"Scope parcial no permitido: scope_from={scope_from}, scope_to={scope_to}. "
            "Ambos deben ser NULL o ambos deben tener valor."
        )
    
    # Modo permisivo: normalizar
    from_str = scope_from.isoformat() if scope_from else ""
    to_str = scope_to.isoformat() if scope_to else ""
    return f"{from_str}_{to_str}"


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
        scope_key = compute_scope_key(scope_from, scope_to)
        q = text("""
            SELECT 
                id, module, dashboard, alert_key,
                scope_from, scope_to, scope_key, status,
                snoozed_until, acknowledged_at, 
                acknowledged_by_auth_user_id, comment, updated_at
            FROM public.auth_alert_states
            WHERE module = :module
              AND dashboard = :dashboard
              AND alert_key = :alert_key
              AND scope_key = :scope_key
        """)
        result = await self.db.execute(q, {
            "module": module,
            "dashboard": dashboard,
            "alert_key": alert_key,
            "scope_key": scope_key,
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
        """
        Obtiene estados para un dashboard/scope con overlay.
        
        Si existe tanto un state global como uno scoped para el mismo alert_key,
        retorna SOLO el scoped (más específico). Usa DISTINCT ON para priorizar.
        
        Prioridad:
        1. scope_key específico (matches :scope_key)
        2. scope_key = 'global' (fallback)
        """
        scope_key = compute_scope_key(scope_from, scope_to, strict=False)
        
        # DISTINCT ON (alert_key) con ORDER BY para priorizar scoped > global
        # (scope_key = :scope_key) devuelve TRUE (1) o FALSE (0), DESC pone TRUE primero
        q = text("""
            SELECT DISTINCT ON (alert_key)
                id, module, dashboard, alert_key,
                scope_from, scope_to, scope_key, status,
                snoozed_until, acknowledged_at,
                acknowledged_by_auth_user_id, comment, updated_at
            FROM public.auth_alert_states
            WHERE module = :module
              AND dashboard = :dashboard
              AND (scope_key = :scope_key OR scope_key = 'global')
            ORDER BY alert_key, (scope_key = :scope_key) DESC, updated_at DESC
        """)
        result = await self.db.execute(q, {
            "module": module,
            "dashboard": dashboard,
            "scope_key": scope_key,
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
        
        Usa scope_key como arbiter canónico para ON CONFLICT:
        - scope_key = 'global' si scope_from/to son NULL
        - scope_key = 'from_to' si tienen fechas
        
        ON CONFLICT (module, dashboard, alert_key, scope_key) siempre funciona.
        
        NOTA: NO hace commit. El caller es responsable.
        """
        scope_key = compute_scope_key(scope_from, scope_to)
        
        q = text("""
            INSERT INTO public.auth_alert_states (
                module, dashboard, alert_key, scope_from, scope_to, scope_key,
                status, snoozed_until, acknowledged_at,
                acknowledged_by_auth_user_id, comment, updated_at
            ) VALUES (
                :module, :dashboard, :alert_key, :scope_from, :scope_to, :scope_key,
                :status, :snoozed_until, :acknowledged_at,
                :acknowledged_by_auth_user_id, :comment, now()
            )
            ON CONFLICT (module, dashboard, alert_key, scope_key)
            DO UPDATE SET
                status = EXCLUDED.status,
                snoozed_until = EXCLUDED.snoozed_until,
                acknowledged_at = EXCLUDED.acknowledged_at,
                acknowledged_by_auth_user_id = EXCLUDED.acknowledged_by_auth_user_id,
                comment = EXCLUDED.comment,
                updated_at = now()
            RETURNING 
                id, module, dashboard, alert_key, scope_from, scope_to, scope_key,
                status, snoozed_until, acknowledged_at,
                acknowledged_by_auth_user_id, comment, updated_at
        """)
        
        result = await self.db.execute(q, {
            "module": module,
            "dashboard": dashboard,
            "alert_key": alert_key,
            "scope_from": scope_from,
            "scope_to": scope_to,
            "scope_key": scope_key,
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
