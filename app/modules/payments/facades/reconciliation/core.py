
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/reconciliation/core.py

Lógica principal de reconciliación.

Autor: Ixchel Beristáin
Fecha: 26/10/2025 (ajustado 20/11/2025)
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.enums import PaymentProvider, PaymentStatus
from app.modules.payments.utils.datetime_helpers import to_iso8601, utcnow, ensure_utc
from .loaders import load_internal_payments, has_success_events
from .rules import normalize_provider_status

logger = logging.getLogger(__name__)


class ReconciliationResult:
    """Resultado de una reconciliación."""

    def __init__(self) -> None:
        self.matched: List[Dict[str, Any]] = []
        self.missing_in_db: List[Dict[str, Any]] = []
        self.missing_in_provider: List[Dict[str, Any]] = []
        self.amount_discrepancies: List[Dict[str, Any]] = []
        self.status_discrepancies: List[Dict[str, Any]] = []
        self.reconciled_at: datetime = utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Serializa el resultado a diccionario."""
        return {
            "reconciled_at": to_iso8601(self.reconciled_at),
            "matched_count": len(self.matched),
            "missing_in_db_count": len(self.missing_in_db),
            "missing_in_provider_count": len(self.missing_in_provider),
            "amount_discrepancies_count": len(self.amount_discrepancies),
            "status_discrepancies_count": len(self.status_discrepancies),
            "matched": self.matched,
            "missing_in_db": self.missing_in_db,
            "missing_in_provider": self.missing_in_provider,
            "amount_discrepancies": self.amount_discrepancies,
            "status_discrepancies": self.status_discrepancies,
        }


async def reconcile_provider_transactions(
    db: AsyncSession,
    *,
    provider: PaymentProvider,
    provider_transactions: List[Dict[str, Any]],
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    # Inyección de dependencias para testing
    load_payments_fn=None,
) -> ReconciliationResult:
    """
    Concilia transacciones del proveedor con registros internos.
    """
    try:
        start_iso = to_iso8601(ensure_utc(start_date)) if start_date else "inicio"
        end_iso = to_iso8601(ensure_utc(end_date)) if end_date else "fin"

        logger.info(
            "🔍 Iniciando reconciliación: provider=%s, transactions=%s, period=%s to %s",
            provider.value,
            len(provider_transactions),
            start_iso,
            end_iso,
        )

        result = ReconciliationResult()

        # 1) Cargar pagos internos del período
        _load_payments = load_payments_fn or load_internal_payments
        internal_payments = await _load_payments(
            db,
            provider=provider,
            start_date=start_date,
            end_date=end_date,
        )

        # Mapear por payment_intent_id (nuestro ID del proveedor)
        internal_by_provider_id = {
            p.payment_intent_id: p
            for p in internal_payments
            if p.payment_intent_id
        }

        logger.debug(
            "Pagos internos cargados: %s (con payment_intent_id: %s)",
            len(internal_payments),
            len(internal_by_provider_id),
        )

        # 2) Comparar transacciones del proveedor
        provider_ids_seen: set[str] = set()

        from decimal import Decimal

        for ext_tx in provider_transactions:
            provider_tx_id = ext_tx.get("id")
            if not provider_tx_id:
                logger.warning("Transacción sin ID: %s", ext_tx)
                continue

            provider_ids_seen.add(provider_tx_id)

            # Buscar en DB
            internal_payment = internal_by_provider_id.get(provider_tx_id)

            if not internal_payment:
                # Falta en DB
                result.missing_in_db.append(
                    {
                        "provider_payment_id": provider_tx_id,
                        "amount": ext_tx.get("amount"),
                        "currency": ext_tx.get("currency"),
                        "status": ext_tx.get("status"),
                        "created_at": ext_tx.get("created_at"),
                    }
                )
                continue

            # Comparar montos con tolerancia pequeña
            ext_amount = ext_tx.get("amount")
            if ext_amount is not None and internal_payment.amount is not None:
                ext_amount_dec = Decimal(str(ext_amount))
                int_amount_dec = Decimal(str(internal_payment.amount))
                difference = abs(ext_amount_dec - int_amount_dec)
                if difference > Decimal("0.01"):
                    result.amount_discrepancies.append(
                        {
                            "payment_id": internal_payment.id,
                            "provider_payment_id": provider_tx_id,
                            "internal_amount": str(int_amount_dec),
                            "provider_amount": str(ext_amount_dec),
                            "difference": str(ext_amount_dec - int_amount_dec),
                        }
                    )

            # Comparar estados (normalizar primero)
            raw_provider_status = (ext_tx.get("status") or "").lower()
            ext_status = normalize_provider_status(provider, ext_tx.get("status"))
            internal_status = internal_payment.status

            non_definitive_provider = raw_provider_status not in {
                "succeeded",
                "completed",
            }
            if (ext_status and ext_status != internal_status) or non_definitive_provider:
                result.status_discrepancies.append(
                    {
                        "payment_id": internal_payment.id,
                        "provider_payment_id": provider_tx_id,
                        "internal_status": internal_status.value,
                        "provider_status": raw_provider_status or None,
                    }
                )

            # Match (se registra aun cuando haya otras discrepancias)
            result.matched.append(
                {
                    "payment_id": internal_payment.id,
                    "provider_payment_id": provider_tx_id,
                    "amount": str(internal_payment.amount),
                    "status": internal_payment.status.value,
                }
            )

        # 3) Identificar pagos en DB que no están en el proveedor
        for payment in internal_payments:
            if payment.payment_intent_id and payment.payment_intent_id not in provider_ids_seen:
                if payment.status in (PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED):
                    result.missing_in_provider.append(
                        {
                            "payment_id": payment.id,
                            "provider_payment_id": payment.payment_intent_id,
                            "amount": str(payment.amount),
                            "status": payment.status.value,
                            "created_at": to_iso8601(payment.created_at),
                        }
                    )

        logger.info(
            "✅ Reconciliación completada: matched=%s, discrepancies=%s",
            len(result.matched),
            len(result.amount_discrepancies)
            + len(result.status_discrepancies)
            + len(result.missing_in_db)
            + len(result.missing_in_provider),
        )

        return result

    except Exception as e:
        logger.exception("❌ Error en reconciliación: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Error en reconciliación: {str(e)}"
        )


async def find_discrepancies(
    db: AsyncSession,
    *,
    provider: PaymentProvider,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    # Inyección de dependencias para testing
    load_payments_fn=None,
    has_success_events_fn=None,
) -> Dict[str, Any]:
    """
    Encuentra discrepancias internas (sin consultar proveedor).
    """
    try:
        start_iso = to_iso8601(ensure_utc(start_date)) if start_date else "inicio"
        end_iso = to_iso8601(ensure_utc(end_date)) if end_date else "fin"

        logger.info(
            "🔍 Buscando discrepancias internas: provider=%s, period=%s to %s",
            provider.value,
            start_iso,
            end_iso,
        )

        discrepancies: Dict[str, list[Dict[str, Any]]] = {
            "succeeded_without_provider_id": [],
            "pending_too_long": [],
            "failed_with_success_events": [],
        }

        _load_payments = load_payments_fn or load_internal_payments
        payments = await _load_payments(
            db,
            provider=provider,
            start_date=start_date,
            end_date=end_date,
        )

        now = utcnow()

        for payment in payments:
            # Pagos SUCCEEDED sin payment_intent_id
            if payment.status == PaymentStatus.SUCCEEDED and not payment.payment_intent_id:
                discrepancies["succeeded_without_provider_id"].append(
                    {
                        "payment_id": payment.id,
                        "user_id": payment.user_id,
                        "amount": str(payment.amount),
                        "created_at": to_iso8601(payment.created_at),
                    }
                )

            # Pagos PENDING muy antiguos (>24h)
            if payment.status == PaymentStatus.PENDING:
                age_hours = (now - payment.created_at).total_seconds() / 3600
                if age_hours > 24:
                    discrepancies["pending_too_long"].append(
                        {
                            "payment_id": payment.id,
                            "user_id": payment.user_id,
                            "amount": str(payment.amount),
                            "created_at": to_iso8601(payment.created_at),
                            "age_hours": int(age_hours),
                        }
                    )

            # Pagos FAILED con eventos de éxito
            if payment.status == PaymentStatus.FAILED:
                _has_success = has_success_events_fn or has_success_events
                success_events = await _has_success(db, payment.id)
                if success_events:
                    discrepancies["failed_with_success_events"].append(
                        {
                            "payment_id": payment.id,
                            "user_id": payment.user_id,
                            "amount": str(payment.amount),
                            "provider_payment_id": payment.payment_intent_id,
                        }
                    )

        total_discrepancies = sum(len(v) for v in discrepancies.values())
        logger.info("✅ Discrepancias encontradas: %s", total_discrepancies)

        return discrepancies

    except Exception as e:
        logger.exception("❌ Error buscando discrepancias: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Error buscando discrepancias: {str(e)}"
        )


__all__ = [
    "ReconciliationResult",
    "reconcile_provider_transactions",
    "find_discrepancies",
]

# Fin del archivo backend/app/modules/payments/facades/reconciliation/core.py
