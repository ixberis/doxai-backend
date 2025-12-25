
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/receipts/generator.py

Generación de recibos PDF (stub) alineada al modelo de pagos actual.

Autor: Ixchel Beristáin
Fecha: 03/11/2025 (ajustado 21/11/2025)
"""

from __future__ import annotations

import logging
import hashlib
from typing import Optional, Dict, Any, Any
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.modules.payments.enums import PaymentStatus
from app.modules.payments.models.payment_models import Payment
from app.modules.payments.repositories.payment_repository import PaymentRepository
from app.modules.payments.utils.datetime_helpers import to_iso8601, utcnow
from .signer import generate_signed_url, SIGNED_URL_EXPIRY_SECONDS

logger = logging.getLogger(__name__)

RECEIPTS_STORAGE_BASE = "receipts"


def generate_receipt_id(payment_id: int) -> str:
    base = f"{payment_id}_{to_iso8601(utcnow())}"
    return hashlib.sha256(base.encode()).hexdigest()[:16]


def get_storage_path(
    payment_id: int,
    receipt_id: str,
    *,
    created_at: Optional[datetime] = None,
) -> str:
    """
    Path estable; si se pasa created_at se usa su año/mes (preferible),
    si no, usa el mes actual (válido para nueva generación).
    """
    ref = created_at or utcnow()
    return (
        f"{RECEIPTS_STORAGE_BASE}/"
        f"{ref.year}/{ref.month:02d}/receipt_{payment_id}_{receipt_id}.pdf"
    )


async def generate_pdf_content(
    payment: Any,
    user_billing_info: Optional[Dict[str, Any]],
    company_info: Optional[Dict[str, Any]],
) -> bytes:
    """
    Stub de generación de PDF.
    En producción se sustituye por una librería PDF.

    Importante:
    - Debe ser robusto ante objetos tipo MockPayment usados en tests.
    """
    logger.warning("⚠️ PDF generation no implementado - usando stub")

    if not company_info:
        company_info = {"name": "DoxAI", "tax_id": "N/A", "address": "N/A"}

    # created_at robusto
    created_at = getattr(payment, "created_at", None) or utcnow()

    # amount robusto (para MockPayment puede no existir)
    raw_amount = getattr(payment, "amount", None)
    try:
        amount_value = float(raw_amount) if raw_amount is not None else 0.0
    except Exception:
        amount_value = 0.0

    # currency robusta
    currency_obj = getattr(payment, "currency", None)
    if hasattr(currency_obj, "value"):
        currency_str = currency_obj.value.upper()
    elif currency_obj is not None:
        currency_str = str(currency_obj).upper()
    else:
        currency_str = "N/A"

    # status robusto
    status_obj = getattr(payment, "status", None)
    if hasattr(status_obj, "value"):
        status_str = status_obj.value
    elif status_obj is not None:
        status_str = str(status_obj)
    else:
        status_str = "unknown"

    # créditos robustos
    credits = getattr(payment, "credits_awarded", None)
    if credits is None:
        credits = getattr(payment, "credits_purchased", None) or 0

    # proveedor robusto
    provider_obj = getattr(payment, "provider", None)
    if hasattr(provider_obj, "value"):
        provider_str = provider_obj.value.upper()
    elif provider_obj is not None:
        provider_str = str(provider_obj).upper()
    else:
        provider_str = "UNKNOWN"

    # ID de transacción robusto
    tx_id = (
        getattr(payment, "payment_intent_id", None)
        or getattr(payment, "provider_payment_id", None)
        or "N/A"
    )

    # Datos de facturación robustos
    user_name = (
        user_billing_info.get("name", "N/A") if user_billing_info else "N/A"
    )
    user_email = (
        user_billing_info.get("email", "N/A") if user_billing_info else "N/A"
    )

    return f"""
    RECIBO DE PAGO - DOXAI
    Payment ID: {getattr(payment, 'id', 'N/A')}
    Fecha: {created_at.strftime('%Y-%m-%d %H:%M:%S')}
    Monto: ${amount_value:.2f} {currency_str}
    Estado: {status_str}
    Créditos: {credits}
    Usuario: {user_name}
    Email: {user_email}
    Proveedor: {provider_str}
    ID Transacción: {tx_id}
    Empresa: {company_info.get('name', 'N/A')}
    RFC: {company_info.get('tax_id', 'N/A')}
    """.encode("utf-8")


async def generate_receipt_pdf(
    payment: Any,
    user_billing_info: Optional[Dict[str, Any]] = None,
    company_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Genera un PDF de recibo y retorna metadata (para compatibilidad con tests).
    Acepta tanto modelos Payment reales como mocks con un subconjunto de atributos.
    """
    payment_id = getattr(payment, "id", None)
    if payment_id is None:
        raise ValueError("payment debe tener un atributo 'id' para generar recibo")

    receipt_id = generate_receipt_id(payment_id)
    storage_path = get_storage_path(
        payment_id,
        receipt_id,
        created_at=getattr(payment, "created_at", None) or utcnow(),
    )

    pdf_data = await generate_pdf_content(payment, user_billing_info, company_info)

    return {
        "storage_path": storage_path,
        "signed_at": to_iso8601(utcnow()),
        "pdf_data": pdf_data,
        "receipt_id": receipt_id,
    }


async def generate_receipt(
    db: AsyncSession,
    *,
    payment_id: int,
    user_billing_info: Optional[Dict[str, Any]] = None,
    company_info: Optional[Dict[str, Any]] = None,
    force_regenerate: bool = False,
    # Inyección de dependencias para testing
    payment_repo: Optional[PaymentRepository] = None,
) -> Dict[str, Any]:
    """
    Genera o regenera un recibo para un pago.

    Reglas:
    - Sólo pagos SUCCEEDED o REFUNDED pueden generar recibo.
    - Si ya existe recibo y no se fuerza la regeneración, devuelve URL nueva
      para el recibo existente.
    """
    try:
        logger.info(
            "📄 Generando recibo: payment_id=%s, force=%s",
            payment_id,
            force_regenerate,
        )

        _payment_repo = payment_repo or PaymentRepository()
        payment = await _payment_repo.get(db, payment_id)

        if not payment:
            raise HTTPException(
                status_code=404, detail=f"Pago no encontrado: {payment_id}"
            )

        if payment.status not in (PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Pago no elegible para recibo: "
                    f"status={payment.status.value}"
                ),
            )

        meta = getattr(payment, "metadata_json", None) or {}
        existing_receipt = meta.get("receipt_url")

        # Renovación de recibo existente (no forzada)
        if existing_receipt and not force_regenerate:
            logger.info("Recibo ya existente para payment_id=%s", payment_id)

            receipt_id = meta.get("receipt_id")
            if receipt_id:
                storage_path = meta.get("receipt_storage_path") or get_storage_path(
                    payment_id,
                    receipt_id,
                    created_at=payment.created_at or utcnow(),
                )
                signed_url = await generate_signed_url(storage_path)
                url_expires_at = to_iso8601(
                    utcnow() + timedelta(seconds=SIGNED_URL_EXPIRY_SECONDS)
                )

                updated_metadata = {
                    **meta,
                    "receipt_url": signed_url,
                    "receipt_url_expires_at": url_expires_at,
                    "receipt_renewed_at": to_iso8601(utcnow()),
                    "receipt_storage_path": storage_path,
                }
                # Persistimos en el Payment real; en mocks simplemente se añade el atributo
                setattr(payment, "metadata_json", updated_metadata)
                await db.flush()

                return {
                    "receipt_id": receipt_id,
                    "receipt_url": signed_url,
                    "storage_path": storage_path,
                    "generated_at": meta.get("receipt_generated_at"),
                    "expires_at": url_expires_at,
                    "already_existed": True,
                }

        # Nueva generación
        pdf_data = await generate_pdf_content(payment, user_billing_info, company_info)
        receipt_checksum = hashlib.sha256(pdf_data).hexdigest()

        receipt_id = generate_receipt_id(payment_id)
        storage_path = get_storage_path(
            payment_id,
            receipt_id,
            created_at=utcnow(),
        )

        logger.warning("⚠️ Upload a storage no implementado - usando stub")

        signed_url = await generate_signed_url(storage_path)
        url_expires_at = to_iso8601(
            utcnow() + timedelta(seconds=SIGNED_URL_EXPIRY_SECONDS)
        )

        updated_metadata = {
            **meta,
            "receipt_id": receipt_id,
            "receipt_url": signed_url,
            "receipt_url_expires_at": url_expires_at,
            "receipt_storage_path": storage_path,
            "receipt_generated_at": to_iso8601(utcnow()),
            "receipt_checksum": receipt_checksum,
        }

        setattr(payment, "metadata_json", updated_metadata)
        await db.flush()

        logger.info(
            "✅ Recibo generado: payment_id=%s, receipt_id=%s",
            payment_id,
            receipt_id,
        )

        return {
            "receipt_id": receipt_id,
            "receipt_url": signed_url,
            "storage_path": storage_path,
            "generated_at": updated_metadata["receipt_generated_at"],
            "expires_at": url_expires_at,
            "receipt_checksum": receipt_checksum,
            "already_existed": False,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("❌ Error generando recibo: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Error generando recibo: {str(e)}"
        )


__all__ = [
    "generate_receipt",
    "generate_receipt_id",
    "get_storage_path",
    "generate_pdf_content",
    "generate_receipt_pdf",
]

# Fin del archivo backend/app/modules/payments/facades/receipts/generator.py

