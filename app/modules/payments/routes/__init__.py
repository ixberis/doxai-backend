
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/routes/__init__.py

Ensamblador de rutas REST v3 del módulo Payments.

Incluye:
- /payments/checkout/start
- /payments/wallet
- /payments/reservations/*
- /payments/refunds/manual
- /payments/webhooks/stripe
- /payments/webhooks/paypal
- /payments/intents/{payment_id}
- /payments/reconciliation/report
- /payments/receipts/*
- /payments/metrics/*

Autor: Ixchel Beristain
Fecha: 2025-11-21
"""

from fastapi import APIRouter

from .checkout import router as checkout_router
from .wallet import router as wallet_router
from .reservations import router as reservations_router
from .refunds import router as refunds_router
from .webhooks_stripe import router as webhooks_stripe_router
from .webhooks_paypal import router as webhooks_paypal_router
from .payments import router as payments_router
from .reconciliation import router as reconciliation_router
from .receipts import router as receipts_router
from .metrics import router as metrics_router  # 👈 métricas v3

router = APIRouter()

# Prefijo común /payments para todas las rutas del módulo
router.include_router(checkout_router, prefix="/payments")
router.include_router(wallet_router, prefix="/payments")
router.include_router(reservations_router, prefix="/payments")
router.include_router(refunds_router, prefix="/payments")
router.include_router(webhooks_stripe_router, prefix="/payments")
router.include_router(webhooks_paypal_router, prefix="/payments")
router.include_router(payments_router, prefix="/payments")
router.include_router(reconciliation_router, prefix="/payments")
router.include_router(receipts_router, prefix="/payments")
router.include_router(metrics_router, prefix="/payments")  # 👈 ahora sí montado

__all__ = ["router"]

# Fin del archivo backend/app/modules/payments/routes/__init__.py