# -*- coding: utf-8 -*-
"""
backend/app/shared/orm/cross_module_relationships.py

Registro de relaciones ORM entre módulos (auth <-> payments).

Este módulo resuelve el problema de dependencias circulares entre modelos
de diferentes módulos. En lugar de definir las relaciones directamente
en los modelos (lo cual requiere que ambos módulos estén importados para
configure_mappers()), las registramos aquí después de que ambos existan.

Esto permite que cada módulo pueda ejecutar configure_mappers() de forma
aislada para sus propios tests, mientras que la aplicación completa
registra las relaciones cross-module al arrancar.

Autor: DoxAI
Fecha: 2025-12-23
"""

from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy.orm import Mapped, relationship

logger = logging.getLogger(__name__)

_RELATIONSHIPS_REGISTERED = False


def register_cross_module_relationships() -> None:
    """
    Registra relaciones ORM entre módulos (auth <-> payments).
    
    Esta función es idempotente: si ya se registraron las relaciones,
    no hace nada en llamadas subsecuentes.
    
    Debe invocarse:
    - En el entrypoint de la app (antes de arrancar FastAPI)
    - En tests de integración que necesiten relaciones cross-module
    
    IMPORTANTE: No invocar antes de que ambos módulos estén importados.
    """
    global _RELATIONSHIPS_REGISTERED
    
    if _RELATIONSHIPS_REGISTERED:
        logger.debug("Cross-module relationships already registered, skipping.")
        return
    
    # Import tardío para evitar ciclos
    from app.modules.auth.models.user_models import AppUser
    from app.modules.payments.models.payment_models import Payment
    from app.modules.payments.models.wallet_models import Wallet
    from app.modules.payments.models.credit_transaction_models import CreditTransaction
    from app.modules.payments.models.usage_reservation_models import UsageReservation
    
    # --- AppUser.payments ---
    if not hasattr(AppUser, "payments") or AppUser.payments is None:
        AppUser.payments = relationship(
            "Payment",
            back_populates="user",
            cascade="all, delete-orphan",
            lazy="selectin",
            foreign_keys=[Payment.user_id],
            overlaps="user",  # Acknowledge bidirectional overlap
        )
        # Configurar back_populates en Payment.user
        if hasattr(Payment, "user") and Payment.user is not None:
            Payment.user.property.back_populates = "payments"
        AppUser.__annotations__["payments"] = Mapped[List["Payment"]]
        logger.debug("Registered AppUser.payments relationship")
    
    # --- AppUser.wallet ---
    if not hasattr(AppUser, "wallet") or AppUser.wallet is None:
        AppUser.wallet = relationship(
            "Wallet",
            back_populates="user",
            uselist=False,
            cascade="all, delete-orphan",
            lazy="selectin",
            foreign_keys=[Wallet.user_id],
            overlaps="user",  # Acknowledge bidirectional overlap
        )
        if hasattr(Wallet, "user") and Wallet.user is not None:
            Wallet.user.property.back_populates = "wallet"
        AppUser.__annotations__["wallet"] = Mapped[Optional["Wallet"]]
        logger.debug("Registered AppUser.wallet relationship")
    
    # --- AppUser.credit_transactions ---
    if not hasattr(AppUser, "credit_transactions") or AppUser.credit_transactions is None:
        AppUser.credit_transactions = relationship(
            "CreditTransaction",
            back_populates="user",
            cascade="all, delete-orphan",
            lazy="selectin",
            foreign_keys=[CreditTransaction.user_id],
            overlaps="user",  # Acknowledge bidirectional overlap
        )
        if hasattr(CreditTransaction, "user") and CreditTransaction.user is not None:
            CreditTransaction.user.property.back_populates = "credit_transactions"
        AppUser.__annotations__["credit_transactions"] = Mapped[List["CreditTransaction"]]
        logger.debug("Registered AppUser.credit_transactions relationship")
    
    # --- AppUser.usage_reservations ---
    if not hasattr(AppUser, "usage_reservations") or AppUser.usage_reservations is None:
        AppUser.usage_reservations = relationship(
            "UsageReservation",
            back_populates="user",
            cascade="all, delete-orphan",
            lazy="selectin",
            foreign_keys=[UsageReservation.user_id],
            overlaps="user",  # Acknowledge bidirectional overlap
        )
        if hasattr(UsageReservation, "user") and UsageReservation.user is not None:
            UsageReservation.user.property.back_populates = "usage_reservations"
        AppUser.__annotations__["usage_reservations"] = Mapped[List["UsageReservation"]]
        logger.debug("Registered AppUser.usage_reservations relationship")
    
    _RELATIONSHIPS_REGISTERED = True
    logger.info("Cross-module ORM relationships registered successfully.")


def reset_registration_flag() -> None:
    """
    Resetea el flag de registro (solo para tests).
    
    NO usar en producción.
    """
    global _RELATIONSHIPS_REGISTERED
    _RELATIONSHIPS_REGISTERED = False


__all__ = ["register_cross_module_relationships", "reset_registration_flag"]
