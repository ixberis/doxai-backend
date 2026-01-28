# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/admin/routes.py

Rutas internas de métricas financieras para Admin → Billing → Finanzas.

Expone endpoints JSON de monitoreo interno:
- /_internal/admin/billing/finance/summary: snapshot de métricas financieras

Sin fallback: la fuente de verdad es solo v_billing_finance_snapshot.
Si la vista falla, responde 500.

v2 (2026-01-28): Added optional from/to query params for dynamic revenue range.

Autor: DoxAI
Fecha: 2026-01-01
"""
import logging
import uuid
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import ProgrammingError

from app.shared.database.database import get_db
from app.modules.auth.dependencies import require_admin_strict
from .schemas import BillingFinanceSnapshot
from .aggregators import BillingFinanceAggregators


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/_internal/admin/billing/finance",
    tags=["admin-billing-finance"],
    dependencies=[Depends(require_admin_strict)],
)


@router.get("/summary", response_model=BillingFinanceSnapshot)
async def get_billing_finance_summary(
    from_date: Optional[str] = Query(
        None,
        alias="from",
        description="Start date (YYYY-MM-DD) for dynamic revenue range",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    to_date: Optional[str] = Query(
        None,
        alias="to",
        description="End date (YYYY-MM-DD) for dynamic revenue range",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Devuelve un snapshot JSON con métricas financieras agregadas.
    
    Fuente de verdad: v_billing_finance_snapshot (1 query) + payments (for range).
    Sin fallback: si la vista no existe, responde 500.
    
    Query params (optional):
    - from: Start date (YYYY-MM-DD) for revenue_range_cents
    - to: End date (YYYY-MM-DD) for revenue_range_cents
    
    Campos:
    - revenue_total_cents, revenue_7d_cents, revenue_30d_cents
    - revenue_range_cents (if from/to provided)
    - currency, checkouts_completed_total, paying_users_total
    - users_activated_total, conversion_activated_to_paid
    - avg_revenue_per_paying_user_cents
    - generated_at
    
    Sin PII. Orientado a negocio, no a debugging.
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[billing_finance_summary:{request_id}] Request started from={from_date} to={to_date}")
    
    # Parse dates if provided
    parsed_from: Optional[date] = None
    parsed_to: Optional[date] = None
    
    if from_date and to_date:
        try:
            parsed_from = date.fromisoformat(from_date)
            parsed_to = date.fromisoformat(to_date)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
        
        if parsed_from > parsed_to:
            raise HTTPException(status_code=400, detail="from_date must be <= to_date")
    
    agg = BillingFinanceAggregators(db)
    
    try:
        snapshot = await agg.get_billing_finance_snapshot(
            from_date=parsed_from,
            to_date=parsed_to,
        )
        
        logger.info(
            f"[billing_finance_summary:{request_id}] source=db_view "
            f"revenue_total={snapshot.revenue_total_cents} "
            f"revenue_7d={snapshot.revenue_7d_cents} "
            f"revenue_30d={snapshot.revenue_30d_cents} "
            f"revenue_range={snapshot.revenue_range_cents} "
            f"paying_users={snapshot.paying_users_total} "
            f"conversion={snapshot.conversion_activated_to_paid:.4f}"
        )
        
        return BillingFinanceSnapshot(
            revenue_total_cents=snapshot.revenue_total_cents,
            revenue_7d_cents=snapshot.revenue_7d_cents,
            revenue_30d_cents=snapshot.revenue_30d_cents,
            revenue_range_cents=snapshot.revenue_range_cents,
            range_from=snapshot.range_from,
            range_to=snapshot.range_to,
            currency=snapshot.currency,
            checkouts_completed_total=snapshot.checkouts_completed_total,
            paying_users_total=snapshot.paying_users_total,
            users_activated_total=snapshot.users_activated_total,
            conversion_activated_to_paid=snapshot.conversion_activated_to_paid,
            avg_revenue_per_paying_user_cents=snapshot.avg_revenue_per_paying_user_cents,
            generated_at=snapshot.generated_at,
        )
        
    except ProgrammingError as e:
        # Vista SQL no existe (error de Postgres)
        logger.error(f"[billing_finance_summary:{request_id}] Vista SQL no existe: {e}")
        raise HTTPException(
            status_code=500,
            detail="Métricas financieras no disponibles: falta vista SQL / migración de v_billing_finance_snapshot.",
        )
        
    except RuntimeError as e:
        # Vista existe pero no retorna datos
        logger.error(f"[billing_finance_summary:{request_id}] {e}")
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
        
    except Exception as e:
        logger.exception(f"[billing_finance_summary:{request_id}] Error inesperado: {e}")
        raise HTTPException(
            status_code=500,
            detail="Métricas financieras no disponibles: error interno.",
        )


# Fin del archivo backend/app/modules/billing/admin/routes.py
