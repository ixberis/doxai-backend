# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/__init__.py

Módulo de billing para gestión de paquetes de créditos y checkout.

Exporta un router unificado que incluye:
- /api/billing/credit-packages
- /api/billing/checkout/start
- /api/billing/webhooks/stripe

Autor: DoxAI
Fecha: 2025-12-29
"""

from fastapi import APIRouter

from .routes import router as billing_router
from .webhook_routes import router as billing_webhook_router

router = APIRouter(tags=["billing"])
router.include_router(billing_router)
router.include_router(billing_webhook_router)

__all__ = ["router"]
