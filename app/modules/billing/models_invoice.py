# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/models_invoice.py

Modelo ORM para billing_invoices.

Almacena snapshots de recibos comerciales estilo OpenAI.
No es un CFDI - solo recibo comercial con datos fiscales opcionales.

Autor: DoxAI
Fecha: 2025-12-31
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String,
    BigInteger,
    DateTime,
    Text,
    JSON,
    Index,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.base import Base


class BillingInvoice(Base):
    """
    Recibo comercial / invoice snapshot.
    
    Almacena un snapshot de los datos al momento de la compra
    para reproducibilidad y auditoría.
    """
    
    __tablename__ = "billing_invoices"
    
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    
    # FK al checkout_intent
    checkout_intent_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        unique=True,
        index=True,
        doc="ID del checkout_intent asociado (1:1 relación).",
    )
    
    # FK a app_users.user_id
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        doc="ID del usuario dueño del recibo.",
    )
    
    # Invoice number legible (DOX-2025-0001)
    invoice_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        doc="Número de recibo legible (DOX-YYYY-NNNN).",
    )
    
    # Snapshot JSON completo
    snapshot_json: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        doc="Snapshot de datos: issuer, bill_to, line_items, totals, payment_details.",
    )
    
    # Timestamps
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        doc="Fecha de emisión del recibo.",
    )
    
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Fecha de pago (si aplica).",
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
    
    __table_args__ = (
        Index("ix_billing_invoices_user_issued", "user_id", "issued_at"),
    )
    
    def __repr__(self) -> str:
        return f"<BillingInvoice id={self.id} number={self.invoice_number} user={self.user_id}>"


__all__ = ["BillingInvoice"]
