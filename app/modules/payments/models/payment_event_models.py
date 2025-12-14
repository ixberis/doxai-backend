
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/models/payment_event_models.py

Registro de eventos provenientes de webhooks de Stripe/PayPal.

Autor: Ixchel Beristain
Fecha: 2025-11-20
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    String,
    Integer,
    ForeignKey,
    DateTime,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.database.base import Base

if TYPE_CHECKING:
    from .payment_models import Payment


class PaymentEvent(Base):
    __tablename__ = "payment_events"

    id: Mapped[int] = mapped_column(primary_key=True)

    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    provider_event_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
        unique=True,
        index=True,
        doc="ID del evento en el proveedor (event.id / webhook.id).",
    )

    event_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
        doc="Tipo de evento (payment_intent.succeeded, refund.completed, ...).",
    )

    payload_json: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        doc="Payload completo del evento normalizado como JSONB.",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="NOW()",
    )

    payment: Mapped["Payment"] = relationship(
        "Payment",
        back_populates="events",
    )

    __table_args__ = (
        UniqueConstraint(
            "provider_event_id",
            name="uq_payment_events_provider_event_id",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - representacional
        return f"<PaymentEvent id={self.id} type={self.event_type}>"
    
# Fin del archivo backend\app\modules\payments\models\payment_event_models.py
