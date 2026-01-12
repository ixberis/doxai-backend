# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/models/checkout_intent.py

Modelo ORM para la tabla checkout_intents.

Autor: DoxAI
Fecha: 2025-12-29
Updated: 2026-01-12 - SSOT: auth_user_id UUID reemplaza user_id BIGINT
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID
from enum import Enum

from sqlalchemy import (
    String,
    BigInteger,
    DateTime,
    Text,
    UniqueConstraint,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.base import Base


class CheckoutIntentStatus(str, Enum):
    """Estados posibles de un checkout intent."""
    CREATED = "created"
    PENDING = "pending"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class CheckoutIntent(Base):
    """
    Intent de checkout para créditos prepagados.
    
    Registra cada intento de checkout antes de que el usuario
    complete el pago. Permite idempotencia y tracking.
    
    SSOT: Ownership via auth_user_id (UUID), NOT user_id (legacy removed).
    Alineado con: database/payments/02_tables/08_checkout_intents.sql
    """
    
    __tablename__ = "checkout_intents"
    
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    
    # SSOT: auth_user_id UUID es el ownership único
    auth_user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        nullable=False,
        index=True,
        doc="UUID del usuario (auth_user_id). SSOT de ownership.",
    )
    
    package_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="ID del paquete de créditos (pkg_starter, pkg_pro, pkg_enterprise).",
    )
    
    idempotency_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Clave idempotente única por usuario.",
    )
    
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=CheckoutIntentStatus.CREATED.value,
        doc="Estado actual: created, pending, completed, expired, cancelled.",
    )
    
    # Provider será null hasta que se integre Stripe/PayPal
    provider: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Proveedor de pago (stripe, paypal) - null hasta integración.",
    )
    
    # ID de sesión del proveedor (e.g., Stripe session ID)
    provider_session_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        doc="ID de sesión del proveedor (stripe session_id, paypal order_id).",
    )
    
    checkout_url: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="URL de checkout generada (dummy o real).",
    )
    
    # Datos del paquete al momento del checkout (snapshot)
    credits_amount: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        doc="Cantidad de créditos del paquete.",
    )
    
    price_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        doc="Precio en centavos al momento del checkout.",
    )
    
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="MXN",
        doc="Moneda del precio (ISO 4217).",
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    
    # Timestamp de confirmación de pago (solo se setea una vez)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        doc="Timestamp de confirmación de pago. Se setea una vez al completar (idempotente).",
    )
    
    __table_args__ = (
        # SSOT: unique constraint por auth_user_id + idempotency_key
        UniqueConstraint(
            "auth_user_id",
            "idempotency_key",
            name="uq_checkout_intent_user_idem",
        ),
        Index("ix_checkout_intents_user_status", "auth_user_id", "status"),
    )
    
    def __repr__(self) -> str:
        return f"<CheckoutIntent id={self.id} auth_user_id={str(self.auth_user_id)[:8]}... package={self.package_id} status={self.status}>"


__all__ = [
    "CheckoutIntent",
    "CheckoutIntentStatus",
]
