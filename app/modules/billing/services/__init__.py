# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/services/__init__.py

Servicios de billing para checkout de créditos.

SSOT: El flujo canónico de checkout usa BillingFinalizeService para crear
Payment + CreditTransaction de forma atómica e idempotente.

IMPORTANTE: Este módulo NO exporta get_admin_notify_email (eliminado).
Para email de admin, usar: from app.shared.services.admin_email_config import get_admin_notification_email

Autor: DoxAI
Fecha: 2025-12-29
Updated: 2026-01-15 - SSOT: Unified checkout flow via BillingFinalizeService
"""

# SSOT: Finalize service es el flujo canónico para checkout completado
from .finalize_service import (
    BillingFinalizeService,
    FinalizeResult,
    finalize_checkout_intent,
)

# Admin notifications (NO get_admin_notify_email - eliminado)
from .admin_notification_service import (
    send_admin_purchase_notification,
)

# Credit services
from app.modules.billing.credits.services import (
    CreditService,
    WalletService,
    ReservationService,
)

__all__ = [
    # SSOT: Canonical checkout finalization
    "BillingFinalizeService",
    "FinalizeResult",
    "finalize_checkout_intent",
    # Admin notifications
    "send_admin_purchase_notification",
    # Credit services
    "CreditService",
    "WalletService",
    "ReservationService",
]
