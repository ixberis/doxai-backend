# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/models/payment.py

Modelo ORM para la tabla payments (SSOT de ingresos).

Autor: DoxAI
Fecha: 2026-01-14
Sincronizado con: database/payments/02_tables/02_payments.sql
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Any
from uuid import UUID
from enum import Enum

from sqlalchemy import (
    String,
    BigInteger,
    Integer,
    Boolean,
    DateTime,
    Text,
    Index,
    UniqueConstraint,
    func,
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.base import Base


class PaymentProvider(str, Enum):
    """
    Proveedores de pago soportados.
    
    Sincronizado con: payment_provider_enum en PostgreSQL
    """
    STRIPE = "stripe"
    PAYPAL = "paypal"


class PaymentStatus(str, Enum):
    """
    Estados del ciclo de vida de un pago.
    
    Sincronizado con: payment_status_enum en PostgreSQL
    """
    CREATED = "created"
    PENDING = "pending"
    AUTHORIZED = "authorized"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class CurrencyEnum(str, Enum):
    """
    Monedas soportadas.
    
    Sincronizado con: currency_enum en PostgreSQL
    """
    MXN = "mxn"
    USD = "usd"


class Payment(Base):
    """
    Registro de pagos confirmados (SSOT de ingresos).
    
    Un Payment se crea cuando un checkout_intent se finaliza exitosamente.
    Es la fuente de verdad para métricas de ingresos.
    
    SSOT: Ownership via auth_user_id (UUID).
    Alineado con: database/payments/02_tables/02_payments.sql
    """
    
    __tablename__ = "payments"
    
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
    
    provider: Mapped[PaymentProvider] = mapped_column(
        SQLEnum(
            PaymentProvider,
            name="payment_provider_enum",
            create_type=False,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        doc="Proveedor de pago (stripe, paypal).",
    )
    
    status: Mapped[PaymentStatus] = mapped_column(
        SQLEnum(
            PaymentStatus,
            name="payment_status_enum",
            create_type=False,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=PaymentStatus.CREATED,
        doc="Estado del pago.",
    )
    
    amount_cents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Monto en centavos.",
    )
    
    currency: Mapped[CurrencyEnum] = mapped_column(
        SQLEnum(
            CurrencyEnum,
            name="currency_enum",
            create_type=False,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=CurrencyEnum.MXN,
        doc="Moneda del pago (ISO 4217 lowercase).",
    )
    
    # IDs del proveedor
    provider_payment_id: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="ID principal reportado por el PSP (ej: Stripe payment_intent).",
    )
    
    provider_transaction_id: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="ID de transacción del PSP (cuando es distinto).",
    )
    
    idempotency_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Clave idempotente única por usuario.",
    )
    
    credits_purchased: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Créditos adquiridos en este pago.",
    )
    
    captured: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="Flag de captura total.",
    )
    
    payment_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="'{}'::jsonb",
        doc="Metadatos adicionales del pago.",
    )
    
    # Timestamps de ciclo de vida
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
    
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Momento en que el pago quedó realizado.",
    )
    
    succeeded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    authorized_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    failed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    refunded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    __table_args__ = (
        # Idempotencia por usuario
        UniqueConstraint(
            "auth_user_id",
            "idempotency_key",
            name="uq_payment_user_idem",
        ),
        # Idempotencia por proveedor
        UniqueConstraint(
            "provider",
            "provider_payment_id",
            name="uq_payment_provider_payment",
        ),
        Index("ix_payments_user_status", "auth_user_id", "status"),
    )
    
    def __repr__(self) -> str:
        return (
            f"<Payment id={self.id} auth_user_id={str(self.auth_user_id)[:8]}... "
            f"provider={self.provider.value} status={self.status.value} "
            f"amount={self.amount_cents} {self.currency.value}>"
        )


__all__ = [
    "Payment",
    "PaymentProvider",
    "PaymentStatus",
    "CurrencyEnum",
]
