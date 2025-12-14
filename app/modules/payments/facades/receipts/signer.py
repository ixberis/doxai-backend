
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/receipts/signer.py

Generación de URLs firmadas para recibos.

Autor: Ixchel Beristáin
Fecha: 26/10/2025 (ajustado 20/11/2025)
"""

from __future__ import annotations

import logging
import hashlib
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.modules.payments.repositories.payment_repository import PaymentRepository
from app.modules.payments.utils.datetime_helpers import utcnow

logger = logging.getLogger(__name__)

SIGNED_URL_EXPIRY_SECONDS = 7 * 24 * 3600  # 7 días


async def generate_signed_url(storage_path: str) -> str:
    """
    Genera una URL firmada temporal (stub).
    En producción: implementar con Supabase Storage o S3.
    """
    logger.warning("⚠️ Signed URL generation no implementado - usando stub")
    expiry_timestamp = int(
        (utcnow() + timedelta(seconds=SIGNED_URL_EXPIRY_SECONDS)).timestamp()
    )
    signature = hashlib.sha256(
        f"{storage_path}_{expiry_timestamp}".encode()
    ).hexdigest()[:16]
    return (
        f"https://storage.doxai.com/"
        f"{storage_path}?expires={expiry_timestamp}&sig={signature}"
    )


def sign_receipt_url(path: str, expires_in: int = SIGNED_URL_EXPIRY_SECONDS) -> str:
    """
    Versión síncrona para tests.
    """
    expiry_timestamp = int(
        (utcnow() + timedelta(seconds=expires_in)).timestamp()
    )
    signature = hashlib.sha256(
        f"{path}_{expiry_timestamp}".encode()
    ).hexdigest()[:16]
    return (
        f"https://storage.doxai.com/"
        f"{path}?expires={expiry_timestamp}&sig={signature}"
    )


def _stable_storage_path(
    payment_id: int,
    receipt_id: str,
    created_at: datetime,
) -> str:
    """
    Construye un path estable usando el año/mes del pago,
    para que coincida con el path usado cuando se generó el recibo.
    """
    return (
        f"receipts/{created_at.year}/{created_at.month:02d}/"
        f"receipt_{payment_id}_{receipt_id}.pdf"
    )


async def get_receipt_url(
    db: AsyncSession,
    *,
    payment_id: int,
) -> str:
    """
    Retorna la URL firmada de un recibo existente o error si no existe.
    """
    try:
        payment_repo = PaymentRepository()
        payment = await payment_repo.get(db, payment_id)

        if not payment:
            raise HTTPException(
                status_code=404, detail=f"Pago no encontrado: {payment_id}"
            )

        meta = payment.metadata_json or {}
        receipt_id = meta.get("receipt_id")
        if not receipt_id:
            raise HTTPException(
                status_code=404,
                detail=f"Recibo no encontrado para payment_id={payment_id}",
            )

        storage_path = meta.get("receipt_storage_path") or _stable_storage_path(
            payment_id=payment_id,
            receipt_id=receipt_id,
            created_at=payment.created_at or utcnow(),
        )

        signed_url = await generate_signed_url(storage_path)
        logger.info("📄 URL de recibo obtenida: payment_id=%s", payment_id)
        return signed_url

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("❌ Error obteniendo recibo: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Error obteniendo recibo: {str(e)}"
        )


__all__ = [
    "generate_signed_url",
    "sign_receipt_url",
    "get_receipt_url",
    "SIGNED_URL_EXPIRY_SECONDS",
]

# Fin del archivo backend/app/modules/payments/facades/receipts/signer.py
