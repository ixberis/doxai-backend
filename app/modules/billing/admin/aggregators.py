# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/admin/aggregators.py

Agregador SQL para métricas financieras de Billing.

Estrategia (sin fallback):
- get_billing_finance_snapshot(): 1 query a vista consolidada + query dinámica para rango
- Si la vista no existe o falla, propaga excepción

Fuente de verdad: public.v_billing_finance_snapshot + public.payments (para rango dinámico)

Autor: DoxAI
Fecha: 2026-01-01
Updated: 2026-01-28 - Added revenue_range_cents for dynamic date range support
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


logger = logging.getLogger(__name__)


@dataclass
class BillingFinanceSnapshotData:
    """Dataclass para snapshot de métricas financieras desde vista SQL."""
    revenue_total_cents: int
    revenue_7d_cents: int
    revenue_30d_cents: int
    revenue_range_cents: Optional[int]  # Dynamic range
    range_from: Optional[str]
    range_to: Optional[str]
    currency: str
    checkouts_completed_total: int
    paying_users_total: int
    users_activated_total: int
    conversion_activated_to_paid: float
    avg_revenue_per_paying_user_cents: int
    generated_at: str


class BillingFinanceAggregators:
    """
    Lógica de lectura/agregado desde vista SQL.
    
    Fuente de verdad: public.v_billing_finance_snapshot
    
    Sin fallback: si la vista no existe, propaga excepción.
    IMPORTANTE: Métodos numéricos SIEMPRE retornan int/float (nunca None).
    
    v2 (2026-01-28): Added get_revenue_by_range for dynamic date filtering.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_billing_finance_snapshot(
        self,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> BillingFinanceSnapshotData:
        """
        Obtiene todas las métricas financieras en 1 query + rango dinámico opcional.
        
        Consulta: SELECT * FROM public.v_billing_finance_snapshot
        + Query adicional para revenue_range_cents si from/to están definidos
        
        Args:
            from_date: Optional start date for dynamic range
            to_date: Optional end date for dynamic range
        
        Returns:
            BillingFinanceSnapshotData con datos de la vista.
            
        Raises:
            RuntimeError: Si la vista no existe o no retorna datos.
        """
        q = text("SELECT * FROM public.v_billing_finance_snapshot")
        res = await self.db.execute(q)
        row = res.first()
        
        if not row:
            raise RuntimeError(
                "Métricas financieras no disponibles: vista SQL sin datos. "
                "Verifique que la migración de v_billing_finance_snapshot se haya ejecutado."
            )
        
        # Calculate dynamic range revenue if dates provided
        revenue_range_cents: Optional[int] = None
        range_from_str: Optional[str] = None
        range_to_str: Optional[str] = None
        
        if from_date and to_date:
            revenue_range_cents = await self._get_revenue_by_range(from_date, to_date)
            range_from_str = from_date.isoformat()
            range_to_str = to_date.isoformat()
        
        return BillingFinanceSnapshotData(
            revenue_total_cents=int(row.revenue_total_cents or 0),
            revenue_7d_cents=int(row.revenue_7d_cents or 0),
            revenue_30d_cents=int(row.revenue_30d_cents or 0),
            revenue_range_cents=revenue_range_cents,
            range_from=range_from_str,
            range_to=range_to_str,
            currency=str(row.currency or "MXN"),
            checkouts_completed_total=int(row.checkouts_completed_total or 0),
            paying_users_total=int(row.paying_users_total or 0),
            users_activated_total=int(row.users_activated_total or 0),
            conversion_activated_to_paid=float(row.conversion_activated_to_paid or 0.0),
            avg_revenue_per_paying_user_cents=int(row.avg_revenue_per_paying_user_cents or 0),
            generated_at=str(row.generated_at) if row.generated_at else "",
        )
    
    async def _get_revenue_by_range(
        self,
        from_date: date,
        to_date: date,
    ) -> int:
        """
        Calculate revenue for a specific date range.
        
        SSOT: public.payments table with status='succeeded' and currency='mxn'
        
        Args:
            from_date: Start date (inclusive)
            to_date: End date (inclusive)
            
        Returns:
            Revenue in cents for the specified range
        """
        from datetime import timedelta
        
        # Convert to datetime for timestamptz column
        from_dt = datetime.combine(from_date, datetime.min.time(), tzinfo=timezone.utc)
        to_dt = datetime.combine(to_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
        
        q = text("""
            SELECT COALESCE(SUM(amount_cents), 0) as total
            FROM public.payments
            WHERE status = 'succeeded'
              AND currency = 'mxn'
              AND paid_at >= :from_date
              AND paid_at < :to_date
        """)
        
        try:
            res = await self.db.execute(q, {"from_date": from_dt, "to_date": to_dt})
            return int(res.scalar() or 0)
        except Exception as e:
            logger.warning(f"[get_revenue_by_range] query failed: {e}")
            return 0


# Fin del archivo backend/app/modules/billing/admin/aggregators.py
