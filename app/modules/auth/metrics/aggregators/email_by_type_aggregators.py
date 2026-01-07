# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/aggregators/email_by_type_aggregators.py

Agregadores para métricas de emails por tipo.
Consulta tabla auth_email_events para obtener counts/latencias por email_type.

Autor: Sistema
Fecha: 2026-01-02
Actualizado: 2026-01-07 - Usar EMAIL_SENT_LIKE_STATUSES centralizado
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.enums.email_event_status_enum import EMAIL_SENT_LIKE_STATUSES

logger = logging.getLogger(__name__)


class EmailByTypeAggregators:
    """
    Agregadores para métricas de emails desglosadas por tipo.
    
    Consulta auth_email_events con filtro de periodo.
    
    Terminología:
    - outbound_total: Correos que llegaron al proveedor (sent/delivered/bounced/complained)
    - failed_total: Correos que fallaron antes de llegar al proveedor
    - pending_total: Correos en cola (transitorio)
    """
    
    # Tipos de email conocidos (para incluir aunque tengan 0 eventos)
    KNOWN_EMAIL_TYPES = [
        "account_activation",
        "account_created",
        "password_reset_request",
        "password_reset_success",
        "welcome",
    ]
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_metrics_by_type(
        self,
        from_date: date,
        to_date: date,
    ) -> Dict[str, Any]:
        """
        Obtiene métricas agregadas por tipo de email.
        
        Args:
            from_date: Fecha inicio (inclusive)
            to_date: Fecha fin (inclusive)
            
        Returns:
            {
                "period_from": "2026-01-01",
                "period_to": "2026-01-02",
                "generated_at": "2026-01-02T18:00:00Z",
                "items": [
                    {
                        "email_type": "account_activation",
                        "outbound_total": 10,  # sent + delivered + bounced + complained
                        "failed_total": 1,
                        "pending_total": 0,
                        "failure_rate": 0.0909,
                        "latency_avg_ms": 2400,
                        "latency_p95_ms": 5200,
                        "latency_count": 10,
                    },
                    ...
                ],
                "totals": {
                    "outbound_total": 40,
                    "failed_total": 2,
                    "pending_total": 0,
                    "failure_rate": 0.05,
                    "latency_avg_ms": ...,
                    "latency_count": ...,
                }
            }
        """
        # Rango inclusivo: from <= created_at < to + 1 day
        from_dt = datetime.combine(from_date, datetime.min.time())
        to_dt = datetime.combine(to_date + timedelta(days=1), datetime.min.time())
        
        # Query agregada por tipo
        # Estados "sent-like": sent, delivered, bounced, complained
        # (bounced/complained son correos que SÍ se enviaron pero tuvieron problema después)
        # Latencia: solo considerar eventos con latency_ms IS NOT NULL (independiente del status final)
        # Esto evita perder latencias cuando el status cambia de sent a delivered
        q = text("""
            SELECT
                email_type::text AS email_type,
                COUNT(*) FILTER (WHERE status = ANY(:sent_like_statuses)) AS outbound_total,
                COUNT(*) FILTER (WHERE status = 'failed') AS failed_total,
                COUNT(*) FILTER (WHERE status = 'pending') AS pending_total,
                AVG(latency_ms) FILTER (WHERE latency_ms IS NOT NULL) AS latency_avg_ms,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) 
                    FILTER (WHERE latency_ms IS NOT NULL) AS latency_p95_ms,
                COUNT(*) FILTER (WHERE latency_ms IS NOT NULL) AS latency_count
            FROM public.auth_email_events
            WHERE created_at >= :from_dt
              AND created_at < :to_dt
            GROUP BY email_type
        """)
        
        result = await self.db.execute(q, {
            "from_dt": from_dt,
            "to_dt": to_dt,
            "sent_like_statuses": list(EMAIL_SENT_LIKE_STATUSES),
        })
        
        rows = result.fetchall()
        
        # Convertir a diccionario por tipo
        metrics_by_type: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            outbound = int(row.outbound_total or 0)
            failed = int(row.failed_total or 0)
            total_attempts = outbound + failed
            
            metrics_by_type[row.email_type] = {
                "email_type": row.email_type,
                "outbound_total": outbound,
                "failed_total": failed,
                "pending_total": int(row.pending_total or 0),
                "failure_rate": round(failed / total_attempts, 4) if total_attempts > 0 else 0.0,
                "latency_avg_ms": round(float(row.latency_avg_ms), 2) if row.latency_avg_ms else None,
                "latency_p95_ms": round(float(row.latency_p95_ms), 2) if row.latency_p95_ms else None,
                "latency_count": int(row.latency_count or 0),
            }
        
        # Construir items con todos los tipos conocidos (incluso si tienen 0)
        items: List[Dict[str, Any]] = []
        for email_type in self.KNOWN_EMAIL_TYPES:
            if email_type in metrics_by_type:
                items.append(metrics_by_type[email_type])
            else:
                # Tipo sin eventos en el periodo
                items.append({
                    "email_type": email_type,
                    "outbound_total": 0,
                    "failed_total": 0,
                    "pending_total": 0,
                    "failure_rate": 0.0,
                    "latency_avg_ms": None,
                    "latency_p95_ms": None,
                    "latency_count": 0,
                })
        
        # Calcular totales
        total_outbound = sum(item["outbound_total"] for item in items)
        total_failed = sum(item["failed_total"] for item in items)
        total_pending = sum(item["pending_total"] for item in items)
        total_attempts = total_outbound + total_failed
        
        # Latencia global (usa latency_ms IS NOT NULL, no filtra por status)
        latency_global = await self._get_global_latency(from_dt, to_dt)
        
        return {
            "period_from": from_date.isoformat(),
            "period_to": to_date.isoformat(),
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "items": items,
            "totals": {
                "outbound_total": total_outbound,
                "failed_total": total_failed,
                "pending_total": total_pending,
                "failure_rate": round(total_failed / total_attempts, 4) if total_attempts > 0 else 0.0,
                "latency_avg_ms": latency_global.get("avg_ms"),
                "latency_p95_ms": latency_global.get("p95_ms"),
                "latency_count": latency_global.get("count", 0),
            }
        }
    
    async def _get_global_latency(
        self,
        from_dt: datetime,
        to_dt: datetime,
    ) -> Dict[str, Any]:
        """
        Calcula latencia global del periodo.
        
        IMPORTANTE: No filtra por status, solo por latency_ms IS NOT NULL.
        Esto evita perder datos de latencia cuando el status cambia
        de 'sent' a 'delivered' (transición monotónica).
        """
        q = text("""
            SELECT
                AVG(latency_ms) AS avg_ms,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_ms,
                COUNT(*) AS count
            FROM public.auth_email_events
            WHERE created_at >= :from_dt
              AND created_at < :to_dt
              AND latency_ms IS NOT NULL
        """)
        
        result = await self.db.execute(q, {
            "from_dt": from_dt,
            "to_dt": to_dt,
        })
        
        row = result.first()
        
        if row and row.count > 0:
            return {
                "avg_ms": round(float(row.avg_ms), 2) if row.avg_ms else None,
                "p95_ms": round(float(row.p95_ms), 2) if row.p95_ms else None,
                "count": int(row.count),
            }
        
        return {"avg_ms": None, "p95_ms": None, "count": 0}


# Fin del archivo
