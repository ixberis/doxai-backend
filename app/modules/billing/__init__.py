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

SSOT para modelos de credits:
- Importar modelos desde: app.modules.billing.models
- Este módulo re-exporta para conveniencia, pero billing.models es el SSOT
  que NO importa services/routers (evita imports circulares).

Autor: DoxAI
Fecha: 2025-12-29
Actualizado: 2026-01-11 (SSOT en billing.models para evitar circular imports)
"""

from fastapi import APIRouter

from .routes import router as billing_router
from .webhook_routes import router as billing_webhook_router
from .public_routes import router as billing_public_router
from .routes.admin_backfill import router as admin_backfill_router

# Re-exports de modelos desde SSOT (billing.models)
# Para imports seguros sin circular, usar: from app.modules.billing.models import Wallet
from .models import (
    Wallet,
    CreditTransaction,
    UsageReservation,
)

# Re-exports de enums y servicios desde credits
from .credits import (
    CreditTxType,
    ReservationStatus,
    WalletRepository,
    CreditTransactionRepository,
    UsageReservationRepository,
    CreditService,
    WalletService,
    ReservationService,
    ReservationResult,
)

router = APIRouter(tags=["billing"])
router.include_router(billing_router)
router.include_router(billing_webhook_router)
router.include_router(billing_public_router)
router.include_router(admin_backfill_router)

__all__ = [
    # Router
    "router",
    # Models (SSOT en billing.models)
    "Wallet",
    "CreditTransaction",
    "UsageReservation",
    # Enums
    "CreditTxType",
    "ReservationStatus",
    # Repositories
    "WalletRepository",
    "CreditTransactionRepository",
    "UsageReservationRepository",
    # Services
    "CreditService",
    "WalletService",
    "ReservationService",
    "ReservationResult",
]
