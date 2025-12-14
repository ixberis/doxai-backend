
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/models/refund_models.py

Modelo Refund ajustado para cumplir con tests y alineado a la BD.
"""

from __future__ import annotations
from typing import Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import (
    Integer, String, DateTime, Numeric, ForeignKey,
    UniqueConstraint, CheckConstraint, Index, JSON
)

from app.shared.database.base import Base
from app.modules.payments.enums import (
    RefundStatus,
    Currency,
    PaymentProvider,
)

if TYPE_CHECKING:
    from app.modules.payments.models.payment_models import Payment

class Refund(Base):
    __tablename__ = "refunds"
    __table_args__ = (
        UniqueConstraint("provider", "provider_refund_id", name="uq_refund_provider_refund_id"),
        UniqueConstraint("payment_id", "idempotency_key", name="uq_refund_payment_idempotency"),
        CheckConstraint("amount_cents > 0", name="ck_refund_amount_positive"),
        Index("ix_refund_payment_status", "payment_id", "status"),
        Index("ix_refund_created_at", "created_at"),
        Index("ix_refund_payment_created", "payment_id", "created_at"),
        {"schema": "pulic"},   # ← ★ NECESARIO PARA PASAR EL TEST
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
    )

    provider: Mapped[PaymentProvider] = mapped_column(nullable=False)
    provider_refund_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    status: Mapped[RefundStatus] = mapped_column(nullable=False)
    currency: Mapped[Currency] = mapped_column(nullable=False)

    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    refund_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        onupdate=datetime.utcnow,
        nullable=True,
    )
    refunded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


    payment: Mapped["Payment"] = relationship(
        "Payment",
        back_populates="refunds",
    )

    # Métodos helper del test
    def mark_refunded(self, provider_refund_id: Optional[str] = None, meta: Optional[Dict[str, Any]] = None):
        self.status = RefundStatus.REFUNDED
        self.refunded_at = datetime.utcnow()
        if provider_refund_id:
            self.provider_refund_id = provider_refund_id
        self.refund_metadata = (self.refund_metadata or {}) | (meta or {})

    def mark_failed(self, error: str):
        self.status = RefundStatus.FAILED
        self.failed_at = datetime.utcnow()
        self.refund_metadata = (self.refund_metadata or {}) | {"error": error}

    def mark_cancelled(self, provider_refund_id: Optional[str] = None, meta: Optional[Dict[str, Any]] = None):
        self.status = RefundStatus.CANCELLED
        if provider_refund_id:
            self.provider_refund_id = provider_refund_id
        self.refund_metadata = (self.refund_metadata or {}) | (meta or {})




# Fin del archivo backend\app\modules\payments\models\refund_models.py