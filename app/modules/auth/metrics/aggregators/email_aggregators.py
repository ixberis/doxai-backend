# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/aggregators/email_aggregators.py

Agregadores SQL para métricas de correos del módulo Auth.

Consulta tablas reales:
- public.account_activations (correos de activación)
- public.app_users (correos de bienvenida)

Autor: Sistema
Fecha: 2025-12-26
Actualizado: 2025-12-27 - Welcome latency (avg/p50/p90/p95 en ms, sin ventana temporal)
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


class EmailAggregators:
    """
    Agregadores para métricas de correos electrónicos.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_email_metrics(self) -> Dict[str, Any]:
        """
        Obtiene métricas agregadas de correos.
        
        Usa lógica "accionable" alineada con el backlog:
        - pending_activation: usuarios NO activados cuyo ÚLTIMO token tiene status='pending'
        - pending_welcome: usuarios activados con welcome_email_status='pending'
        - failed_activation: usuarios NO activados cuyo ÚLTIMO token tiene status='failed'
        - failed_welcome: usuarios activados con welcome_email_status='failed'
        
        Returns:
            {
                "total_sent": int,
                "activation_sent": int,
                "welcome_sent": int,
                "failed": int,
                "pending": int,
                ...
                "welcome_latency_count": int,
                "welcome_latency_avg_ms": float|null,
                "welcome_latency_p50_ms": float|null,
                "welcome_latency_p90_ms": float|null,
                "welcome_latency_p95_ms": float|null,
            }
        """
        q = text("""
            SELECT
                -- Activation emails sent (cualquier token enviado)
                (SELECT COUNT(*) FROM public.account_activations 
                 WHERE activation_email_sent_at IS NOT NULL) AS activation_sent,
                
                -- Welcome emails sent
                (SELECT COUNT(*) FROM public.app_users 
                 WHERE welcome_email_sent_at IS NOT NULL) AS welcome_sent,
                
                -- Pending activation (actionable): usuarios NO activados, último token = pending
                (SELECT COUNT(*) FROM (
                    SELECT DISTINCT ON (u.user_id)
                        u.user_id,
                        a.activation_email_status AS status
                    FROM public.account_activations a
                    JOIN public.app_users u ON a.user_id = u.user_id
                    WHERE u.user_is_activated = false
                    ORDER BY u.user_id, a.created_at DESC
                ) AS latest_activation
                WHERE status = 'pending') AS pending_activation,
                
                -- Pending welcome (actionable): usuarios activados con welcome pending
                (SELECT COUNT(*) FROM public.app_users
                 WHERE user_is_activated = true
                   AND welcome_email_status = 'pending') AS pending_welcome,
                
                -- Failed activation (actionable): usuarios NO activados, último token = failed
                (SELECT COUNT(*) FROM (
                    SELECT DISTINCT ON (u.user_id)
                        u.user_id,
                        a.activation_email_status AS status
                    FROM public.account_activations a
                    JOIN public.app_users u ON a.user_id = u.user_id
                    WHERE u.user_is_activated = false
                    ORDER BY u.user_id, a.created_at DESC
                ) AS latest_activation_failed
                WHERE status = 'failed') AS failed_activation,
                
                -- Failed welcome (actionable): usuarios activados con welcome failed
                (SELECT COUNT(*) FROM public.app_users
                 WHERE user_is_activated = true
                   AND welcome_email_status = 'failed') AS failed_welcome
        """)
        
        res = await self.db.execute(q)
        row = res.first()
        
        # Get welcome latency metrics (sin ventana temporal)
        latency = await self._get_welcome_latency()
        
        if row:
            activation_sent = int(row.activation_sent or 0)
            welcome_sent = int(row.welcome_sent or 0)
            pending_activation = int(row.pending_activation or 0)
            pending_welcome = int(row.pending_welcome or 0)
            failed_activation = int(row.failed_activation or 0)
            failed_welcome = int(row.failed_welcome or 0)
            
            return {
                "total_sent": activation_sent + welcome_sent,
                "activation_sent": activation_sent,
                "welcome_sent": welcome_sent,
                "failed": failed_activation + failed_welcome,
                "pending": pending_activation + pending_welcome,
                # Breakdown para debug
                "pending_activation": pending_activation,
                "pending_welcome": pending_welcome,
                "failed_activation": failed_activation,
                "failed_welcome": failed_welcome,
                # Welcome latency (top-level, sin SLA/ventana)
                **latency,
            }
        
        return {
            "total_sent": 0,
            "activation_sent": 0,
            "welcome_sent": 0,
            "failed": 0,
            "pending": 0,
            "pending_activation": 0,
            "pending_welcome": 0,
            "failed_activation": 0,
            "failed_welcome": 0,
            **latency,
        }

    async def _get_welcome_latency(self) -> Dict[str, Any]:
        """
        Calcula latencia de welcome emails usando timestamps internos.
        
        latency = welcome_email_sent_at - user_activated_at (en ms)
        
        Filtro estricto (sin ventana temporal):
        - user_is_activated = true
        - user_activated_at IS NOT NULL
        - welcome_email_sent_at IS NOT NULL
        
        Returns:
            {
                "welcome_latency_count": int,
                "welcome_latency_avg_ms": float | None,
                "welcome_latency_p50_ms": float | None,
                "welcome_latency_p90_ms": float | None,
                "welcome_latency_p95_ms": float | None,
            }
        """
        q = text("""
            SELECT
                COUNT(*) AS latency_count,
                AVG(EXTRACT(EPOCH FROM (welcome_email_sent_at - user_activated_at)) * 1000.0) AS avg_ms,
                PERCENTILE_CONT(0.5) WITHIN GROUP (
                    ORDER BY EXTRACT(EPOCH FROM (welcome_email_sent_at - user_activated_at)) * 1000.0
                ) AS p50_ms,
                PERCENTILE_CONT(0.9) WITHIN GROUP (
                    ORDER BY EXTRACT(EPOCH FROM (welcome_email_sent_at - user_activated_at)) * 1000.0
                ) AS p90_ms,
                PERCENTILE_CONT(0.95) WITHIN GROUP (
                    ORDER BY EXTRACT(EPOCH FROM (welcome_email_sent_at - user_activated_at)) * 1000.0
                ) AS p95_ms
            FROM public.app_users
            WHERE user_is_activated = true
              AND user_activated_at IS NOT NULL
              AND welcome_email_sent_at IS NOT NULL
              AND welcome_email_sent_at >= user_activated_at
        """)
        
        res = await self.db.execute(q)
        row = res.first()
        
        if row and row.latency_count > 0:
            return {
                "welcome_latency_count": int(row.latency_count),
                "welcome_latency_avg_ms": float(row.avg_ms) if row.avg_ms is not None else None,
                "welcome_latency_p50_ms": float(row.p50_ms) if row.p50_ms is not None else None,
                "welcome_latency_p90_ms": float(row.p90_ms) if row.p90_ms is not None else None,
                "welcome_latency_p95_ms": float(row.p95_ms) if row.p95_ms is not None else None,
            }
        
        return {
            "welcome_latency_count": 0,
            "welcome_latency_avg_ms": None,
            "welcome_latency_p50_ms": None,
            "welcome_latency_p90_ms": None,
            "welcome_latency_p95_ms": None,
        }

    async def get_backlog(
        self,
        email_type: str = "all",  # activation|welcome|all
        status: str = "pending",  # pending|failed
        page: int = 1,
        per_page: int = 50,
    ) -> Dict[str, Any]:
        """
        Obtiene lista paginada de correos pendientes/fallidos.
        
        Returns:
            {
                "items": [...],
                "total": int,
                "page": int,
                "per_page": int
            }
        """
        offset = (page - 1) * per_page
        items: List[Dict[str, Any]] = []
        total = 0
        
        # Build queries based on type
        if email_type in ("activation", "all"):
            # Use DISTINCT ON to get only the latest activation attempt per user
            # ONLY show users who:
            # 1. Are NOT yet activated (user_is_activated = false)
            # 2. Their LATEST token has status = pending/failed (not 'sent')
            activation_q = text("""
                SELECT 
                    user_id,
                    email,
                    name,
                    email_type,
                    status,
                    attempts,
                    sent_at,
                    last_error,
                    created_at
                FROM (
                    SELECT DISTINCT ON (u.user_id)
                        u.user_id::text AS user_id,
                        u.user_email AS email,
                        u.user_full_name AS name,
                        'activation' AS email_type,
                        a.activation_email_status::text AS status,
                        a.activation_email_attempts AS attempts,
                        a.activation_email_sent_at::text AS sent_at,
                        a.activation_email_last_error AS last_error,
                        a.created_at::text AS created_at
                    FROM public.account_activations a
                    JOIN public.app_users u ON a.user_id = u.user_id
                    WHERE u.user_is_activated = false
                    ORDER BY u.user_id, a.created_at DESC
                ) AS latest_activations
                WHERE status = :status
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """)
            
            # Count distinct users with latest token matching status
            # (excludes already activated users)
            count_activation_q = text("""
                SELECT COUNT(*) FROM (
                    SELECT DISTINCT ON (u.user_id)
                        u.user_id,
                        a.activation_email_status AS status
                    FROM public.account_activations a
                    JOIN public.app_users u ON a.user_id = u.user_id
                    WHERE u.user_is_activated = false
                    ORDER BY u.user_id, a.created_at DESC
                ) AS latest
                WHERE status = :status
            """)
            
            res = await self.db.execute(
                activation_q, 
                {"status": status, "limit": per_page, "offset": offset}
            )
            for row in res.fetchall():
                items.append({
                    "user_id": row.user_id,
                    "email": row.email,
                    "name": row.name,
                    "email_type": row.email_type,
                    "status": row.status,
                    "attempts": row.attempts,
                    "sent_at": row.sent_at,
                    "last_error": row.last_error,
                    "created_at": row.created_at,
                })
            
            count_res = await self.db.execute(count_activation_q, {"status": status})
            total += count_res.scalar() or 0
        
        if email_type in ("welcome", "all"):
            welcome_q = text("""
                SELECT 
                    u.user_id::text AS user_id,
                    u.user_email AS email,
                    u.user_full_name AS name,
                    'welcome' AS email_type,
                    u.welcome_email_status::text AS status,
                    u.welcome_email_attempts AS attempts,
                    u.welcome_email_sent_at::text AS sent_at,
                    u.welcome_email_last_error AS last_error,
                    u.user_created_at::text AS created_at
                FROM public.app_users u
                WHERE u.welcome_email_status = :status
                  AND u.user_is_activated = true
                ORDER BY u.user_created_at DESC
                LIMIT :limit OFFSET :offset
            """)
            
            count_welcome_q = text("""
                SELECT COUNT(*) FROM public.app_users
                WHERE welcome_email_status = :status
                  AND user_is_activated = true
            """)
            
            res = await self.db.execute(
                welcome_q,
                {"status": status, "limit": per_page, "offset": offset}
            )
            for row in res.fetchall():
                items.append({
                    "user_id": row.user_id,
                    "email": row.email,
                    "name": row.name,
                    "email_type": row.email_type,
                    "status": row.status,
                    "attempts": row.attempts,
                    "sent_at": row.sent_at,
                    "last_error": row.last_error,
                    "created_at": row.created_at,
                })
            
            count_res = await self.db.execute(count_welcome_q, {"status": status})
            total += count_res.scalar() or 0
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
        }


# Fin del archivo
