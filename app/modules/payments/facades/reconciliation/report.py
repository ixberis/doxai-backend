
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/reconciliation/report.py

Generación de reportes de reconciliación.

Autor: Ixchel Beristáin
Fecha: 26/10/2025 (ajustado 20/11/2025)
"""

from __future__ import annotations

import logging
from typing import Dict, Any
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.enums import PaymentProvider, PaymentStatus
from app.modules.payments.utils.datetime_helpers import to_iso8601, utcnow
from .core import find_discrepancies
from .loaders import load_internal_payments

logger = logging.getLogger(__name__)


async def generate_reconciliation_report(
    db: AsyncSession,
    *,
    provider: PaymentProvider,
    start_date: datetime,
    end_date: datetime,
    include_matched: bool = False,
) -> Dict[str, Any]:
    """
    Genera un reporte completo de reconciliación para auditoría.
    """
    try:
        logger.info(
            "📊 Generando reporte de reconciliación: provider=%s, period=%s to %s",
            provider.value,
            to_iso8601(start_date),
            to_iso8601(end_date),
        )

        discrepancies = await find_discrepancies(
            db,
            provider=provider,
            start_date=start_date,
            end_date=end_date,
        )

        payments = await load_internal_payments(
            db,
            provider=provider,
            start_date=start_date,
            end_date=end_date,
        )

        from decimal import Decimal

        total_amount = sum(Decimal(str(p.amount or 0)) for p in payments)
        succeeded_payments = [
            p for p in payments if p.status == PaymentStatus.SUCCEEDED
        ]
        succeeded_amount = sum(
            Decimal(str(p.amount or 0)) for p in succeeded_payments
        )

        report: Dict[str, Any] = {
            "report_generated_at": to_iso8601(utcnow()),
            "provider": provider.value,
            "period": {
                "start": to_iso8601(start_date),
                "end": to_iso8601(end_date),
            },
            "summary": {
                "total_payments": len(payments),
                "total_amount": str(total_amount),
                "succeeded_payments": len(succeeded_payments),
                "succeeded_amount": str(succeeded_amount),
                "pending_payments": len(
                    [p for p in payments if p.status == PaymentStatus.PENDING]
                ),
                "failed_payments": len(
                    [p for p in payments if p.status == PaymentStatus.FAILED]
                ),
                "refunded_payments": len(
                    [p for p in payments if p.status == PaymentStatus.REFUNDED]
                ),
            },
            "discrepancies": discrepancies,
        }

        if include_matched:
            report["all_payments"] = [
                {
                    "payment_id": p.id,
                    "provider_payment_id": p.payment_intent_id,
                    "amount": str(p.amount),
                    "status": p.status.value,
                    "created_at": to_iso8601(p.created_at),
                }
                for p in payments
            ]

        logger.info(
            "✅ Reporte generado: %s pagos, %s discrepancias",
            len(payments),
            sum(len(v) for v in discrepancies.values()),
        )

        return report

    except Exception as e:
        logger.exception("❌ Error generando reporte: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Error generando reporte: {str(e)}"
        )


__all__ = ["generate_reconciliation_report"]

# Fin del archivo backend/app/modules/payments/facades/reconciliation/report.py
