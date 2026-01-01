# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/__init__.py

Módulo de billing para gestión de paquetes de créditos y checkout.

Exporta un router unificado que incluye:
- /api/billing/credit-packages
- /api/billing/checkout/start
- /api/billing/webhooks/stripe
- /api/billing/receipts/public/{token}.pdf (público)
- /api/billing/receipts/public/{token}.json (público)

Autor: DoxAI
Fecha: 2025-12-29
Actualizado: 2026-01-01 (rutas públicas de recibos)
"""

from fastapi import APIRouter

from .routes import router as billing_router
from .webhook_routes import router as billing_webhook_router
from .public_routes import router as billing_public_router

router = APIRouter(tags=["billing"])
router.include_router(billing_router)
router.include_router(billing_webhook_router)
router.include_router(billing_public_router)

__all__ = ["router"]
