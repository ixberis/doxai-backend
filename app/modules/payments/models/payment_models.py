
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/models/payment_models.py

Modelo ORM para la tabla payments.

Autor: Ixchel Beristain
Fecha: 2025-11-20 (ajustado 2025-11-21)
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    String,
    Integer,
    BigInteger,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
    Boolean,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.database.base import Base
from app.modules.payments.enums import Currency, PaymentProvider, PaymentStatus

if TYPE_CHECKING:
    from .payment_event_models import PaymentEvent
    from .refund_models import Refund
    from app.modules.auth.models.user_models import AppUser


class Payment(Base):
    """Pago registrado en el sistema (Stripe / PayPal)."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # FK a app_users.user_id (BIGINT)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("app_users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="ID del usuario (app_users.user_id) que realizó el pago.",
    )

    provider: Mapped[PaymentProvider] = mapped_column(
        PaymentProvider.as_pg_enum(),
        nullable=False,
    )

    status: Mapped[PaymentStatus] = mapped_column(
        PaymentStatus.as_pg_enum(),
        nullable=False,
        index=True,
    )

    currency: Mapped[Currency] = mapped_column(
        Currency.as_pg_enum(),
        nullable=False,
    )

    # Monto en centavos (alineado con SQL: amount_cents)
    amount_cents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Monto total cobrado en centavos.",
    )

    # Créditos comprados (alineado con SQL: credits_purchased)
    credits_purchased: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        doc="Créditos que se acreditan/van a acreditar tras éxito.",
    )

    # ID del pago en el proveedor (alineado con SQL: provider_payment_id)
    provider_payment_id: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="ID del intent/orden en el proveedor (Stripe, PayPal).",
    )

    # ID de transacción del proveedor
    provider_transaction_id: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="ID de transacción del PSP (cuando es distinto de provider_payment_id).",
    )

    idempotency_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Clave idempotente generada por el backend.",
    )

    # Flag de captura
    captured: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        doc="Indica si el pago fue capturado/liquidado.",
    )

    # Metadata (alineado con SQL: payment_metadata)
    payment_metadata: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="'{}'::jsonb",
        doc="Payload normalizado de checkout / datos adicionales.",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="NOW()",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="NOW()",
    )

    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Momento en que el pago quedó realizado.",
    )

    refunded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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

    # FASE 1: Timestamp de verificación del webhook
    webhook_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Momento en que el webhook fue verificado exitosamente.",
    )

    # Relaciones (back_populates con AppUser se configura en el bootstrap ORM)
    user: Mapped["AppUser"] = relationship(
        "AppUser",
        foreign_keys=[user_id],
        lazy="noload",
    )

    events: Mapped[List["PaymentEvent"]] = relationship(
        "PaymentEvent",
        back_populates="payment",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    refunds: Mapped[List["Refund"]] = relationship(
        "Refund",
        back_populates="payment",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_payment_id",
            name="uq_payment_provider_payment",
        ),
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_payment_user_idem",
        ),
        Index("ix_payments_user_status", "user_id", "status"),
    )

    # Propiedades de compatibilidad para código que use nombres anteriores
    @property
    def amount(self) -> float:
        """Monto en unidades (no centavos) para compatibilidad."""
        return self.amount_cents / 100.0 if self.amount_cents else 0.0

    @property
    def credits_awarded(self) -> int:
        """Alias para compatibilidad con código que use credits_awarded."""
        return self.credits_purchased

    @property
    def payment_intent_id(self) -> Optional[str]:
        """Alias para compatibilidad con código que use payment_intent_id."""
        return self.provider_payment_id

    @property
    def metadata_json(self) -> Optional[dict]:
        """Alias para compatibilidad con código que use metadata_json."""
        return self.payment_metadata

    def __repr__(self) -> str:
        return f"<Payment id={self.id} provider={self.provider} status={self.status}>"

# Fin del archivo backend\app\modules\payments\models\payment_models.py
