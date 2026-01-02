# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/admin/aggregators.py

Agregador SQL para métricas financieras de Billing.

Estrategia (sin fallback):
- get_billing_finance_snapshot(): 1 query a vista consolidada
- Si la vista no existe o falla, propaga excepción

Fuente de verdad: public.v_billing_finance_snapshot

Autor: DoxAI
Fecha: 2026-01-01
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


logger = logging.getLogger(__name__)


@dataclass
class BillingFinanceSnapshotData:
    """Dataclass para snapshot de métricas financieras desde vista SQL."""
    revenue_total_cents: int
    revenue_7d_cents: int
    revenue_30d_cents: int
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
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_billing_finance_snapshot(self) -> BillingFinanceSnapshotData:
        """
        Obtiene todas las métricas financieras en 1 query.
        
        Consulta: SELECT * FROM public.v_billing_finance_snapshot
        
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
        
        return BillingFinanceSnapshotData(
            revenue_total_cents=int(row.revenue_total_cents or 0),
            revenue_7d_cents=int(row.revenue_7d_cents or 0),
            revenue_30d_cents=int(row.revenue_30d_cents or 0),
            currency=str(row.currency or "MXN"),
            checkouts_completed_total=int(row.checkouts_completed_total or 0),
            paying_users_total=int(row.paying_users_total or 0),
            users_activated_total=int(row.users_activated_total or 0),
            conversion_activated_to_paid=float(row.conversion_activated_to_paid or 0.0),
            avg_revenue_per_paying_user_cents=int(row.avg_revenue_per_paying_user_cents or 0),
            generated_at=str(row.generated_at) if row.generated_at else "",
        )


# Fin del archivo backend/app/modules/billing/admin/aggregators.py
