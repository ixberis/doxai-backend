
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/receipts/eligibility.py

Validación de elegibilidad para generación de recibos.

Autor: Ixchel Beristáin
Fecha: 26/10/2025 (ajustado 20/11/2025)
"""

from typing import Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.enums import PaymentStatus
from .generator import generate_receipt


def is_eligible_for_receipt(status: PaymentStatus) -> bool:
    """
    Determina si un pago es elegible para generar recibo.

    Un pago es elegible cuando:
    - fue exitoso (SUCCEEDED), o
    - fue reembolsado (REFUNDED).
    """
    return status in (PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED)


async def regenerate_receipt(
    db: AsyncSession,
    *,
    payment_id: int,
    user_billing_info: Optional[Dict[str, Any]] = None,
    company_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Regenera un recibo (útil para cambios en datos fiscales).
    """
    return await generate_receipt(
        db,
        payment_id=payment_id,
        user_billing_info=user_billing_info,
        company_info=company_info,
        force_regenerate=True,
    )


__all__ = ["is_eligible_for_receipt", "regenerate_receipt"]

# Fin del archivo backend/app/modules/payments/facades/receipts/eligibility.py