
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/routes/webhooks_paypal.py

Webhook endpoint para PayPal.

Endpoint:
- POST /payments/webhooks/paypal

FASE 3: Incluye rate limiting y métricas.

Autor: Ixchel Beristain
Fecha: 2025-11-21 (actualizado 2025-12-13)
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_async_session
from app.modules.payments.enums import PaymentProvider
from app.modules.payments.repositories import (
    PaymentRepository,
    RefundRepository,
    PaymentEventRepository,
    WalletRepository,
    CreditTransactionRepository,
)
from app.modules.payments.services import (
    PaymentService,
    RefundService,
    PaymentEventService,
    WalletService,
    CreditService,
)
from app.modules.payments.facades.payments import handle_webhook
from app.modules.payments.facades.payments.webhook_handler import WebhookSignatureError
from app.modules.payments.middleware import check_webhook_rate_limit
from app.modules.payments.metrics.helpers import (
    map_webhook_result_to_metrics,
    get_verification_and_outcome,
    WebhookMetricResult,
)
from app.modules.payments.metrics.exporters.prometheus_exporter import (
    observe_webhook_received,
    observe_webhook_verified,
    observe_webhook_outcome,
    observe_webhook_rejected,
    WEBHOOKS_PROCESSING_SECONDS,
)

router = APIRouter(
    prefix="/webhooks",
    tags=["payments:webhooks"],
)


def build_webhook_services():
    payment_repo = PaymentRepository()
    refund_repo = RefundRepository()
    event_repo = PaymentEventRepository()
    wallet_repo = WalletRepository()
    credit_repo = CreditTransactionRepository()

    credit_service = CreditService(credit_repo)
    wallet_service = WalletService(wallet_repo=wallet_repo, credit_repo=credit_repo)
    payment_service = PaymentService(
        payment_repo=payment_repo,
        wallet_repo=wallet_repo,
        wallet_service=wallet_service,
        credit_service=credit_service,
    )
    refund_service = RefundService(
        refund_repo=refund_repo,
        payment_repo=payment_repo,
        credit_service=credit_service,
    )
    event_service = PaymentEventService(event_repo=event_repo)

    return payment_repo, refund_repo, payment_service, refund_service, event_service


@router.post(
    "/paypal",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(check_webhook_rate_limit)],
)
async def paypal_webhook(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> Dict[str, Any]:
    """
    Webhook de PayPal para notificar pagos y refunds.
    
    Rate limited: 10 req/s por IP (configurable).
    BLOQUE C: Métricas integradas a Prometheus global.
    """
    import time
    
    observe_webhook_received("paypal")
    
    raw_body = await request.body()
    headers = dict(request.headers)

    (
        payment_repo,
        refund_repo,
        payment_service,
        refund_service,
        event_service,
    ) = build_webhook_services()

    start_time = time.time()
    
    try:
        result = await handle_webhook(
            session=session,
            provider=PaymentProvider.PAYPAL,
            raw_body=raw_body,
            headers=headers,
            payment_service=payment_service,
            payment_repo=payment_repo,
            refund_service=refund_service,
            refund_repo=refund_repo,
            event_service=event_service,
        )
        
        duration = time.time() - start_time
        
        # BLOQUE C+: Mapear resultado a métricas separadas (verified vs outcome)
        metric_result, description = map_webhook_result_to_metrics(result)
        verification, outcome = get_verification_and_outcome(metric_result)
        observe_webhook_verified("paypal", verification.value, duration)
        observe_webhook_outcome("paypal", outcome.value)
        
        return result
        
    except WebhookSignatureError as e:
        duration = time.time() - start_time
        observe_webhook_rejected("paypal", "invalid_signature")
        WEBHOOKS_PROCESSING_SECONDS.labels(provider="paypal").observe(duration)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception as e:
        duration = time.time() - start_time
        observe_webhook_rejected("paypal", "processing_error")
        WEBHOOKS_PROCESSING_SECONDS.labels(provider="paypal").observe(duration)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# Fin del archivo backend/app/modules/payments/routes/webhooks_paypal.py
