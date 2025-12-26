# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/aggregators/email_aggregators.py

Agregadores SQL para métricas de correos del módulo Auth.

Consulta tablas reales:
- public.account_activations (correos de activación)
- public.app_users (correos de bienvenida)

Autor: Sistema
Fecha: 2025-12-26
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

    async def get_email_metrics(self) -> Dict[str, int]:
        """
        Obtiene métricas agregadas de correos.
        
        Returns:
            {
                "total_sent": int,
                "activation_sent": int,
                "welcome_sent": int,
                "failed": int,
                "pending": int
            }
        """
        q = text("""
            SELECT
                -- Activation emails sent
                (SELECT COUNT(*) FROM public.account_activations 
                 WHERE activation_email_sent_at IS NOT NULL) AS activation_sent,
                -- Welcome emails sent
                (SELECT COUNT(*) FROM public.app_users 
                 WHERE welcome_email_sent_at IS NOT NULL) AS welcome_sent,
                -- Failed emails (activation + welcome)
                (SELECT COUNT(*) FROM public.account_activations 
                 WHERE activation_email_status = 'failed') +
                (SELECT COUNT(*) FROM public.app_users 
                 WHERE welcome_email_status = 'failed') AS failed,
                -- Pending emails (activation + welcome)
                (SELECT COUNT(*) FROM public.account_activations 
                 WHERE activation_email_status = 'pending') +
                (SELECT COUNT(*) FROM public.app_users 
                 WHERE welcome_email_status = 'pending') AS pending
        """)
        
        res = await self.db.execute(q)
        row = res.first()
        
        if row:
            activation_sent = int(row.activation_sent or 0)
            welcome_sent = int(row.welcome_sent or 0)
            return {
                "total_sent": activation_sent + welcome_sent,
                "activation_sent": activation_sent,
                "welcome_sent": welcome_sent,
                "failed": int(row.failed or 0),
                "pending": int(row.pending or 0),
            }
        
        return {
            "total_sent": 0,
            "activation_sent": 0,
            "welcome_sent": 0,
            "failed": 0,
            "pending": 0,
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
            activation_q = text("""
                SELECT 
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
                WHERE a.activation_email_status = :status
                ORDER BY a.created_at DESC
                LIMIT :limit OFFSET :offset
            """)
            
            count_activation_q = text("""
                SELECT COUNT(*) FROM public.account_activations
                WHERE activation_email_status = :status
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
