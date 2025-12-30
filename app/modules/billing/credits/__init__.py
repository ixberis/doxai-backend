# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/credits/__init__.py

Submódulo de créditos para billing.

Contiene:
- Modelos ORM: Wallet, CreditTransaction, UsageReservation
- Repositorios: WalletRepository, CreditTransactionRepository, UsageReservationRepository
- Servicios: CreditService, WalletService, ReservationService
- Enums: CreditTxType, ReservationStatus

Autor: DoxAI
Fecha: 2025-12-30
"""

from .models import (
    Wallet,
    CreditTransaction,
    UsageReservation,
)
from .enums import (
    CreditTxType,
    ReservationStatus,
)
from .repositories import (
    WalletRepository,
    CreditTransactionRepository,
    UsageReservationRepository,
)
from .services import (
    CreditService,
    WalletService,
    ReservationService,
    ReservationResult,
)

__all__ = [
    # Models
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
