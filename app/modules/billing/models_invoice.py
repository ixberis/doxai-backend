# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/models_invoice.py

Modelo ORM para billing_invoices.

Almacena snapshots de recibos comerciales estilo OpenAI.
No es un CFDI - solo recibo comercial con datos fiscales opcionales.

Autor: DoxAI
Fecha: 2025-12-31
Actualizado: 2026-01-01 (public_token para enlaces públicos)
Updated: 2026-01-12 - SSOT: auth_user_id UUID replaces user_id
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    String,
    BigInteger,
    DateTime,
    Text,
    JSON,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.base import Base


class BillingInvoice(Base):
    """
    Recibo comercial / invoice snapshot.
    
    Almacena un snapshot de los datos al momento de la compra
    para reproducibilidad y auditoría.
    
    SSOT: Uses auth_user_id (UUID) for ownership.
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
    
    # SSOT: auth_user_id UUID for ownership
    auth_user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        nullable=False,
        index=True,
        doc="UUID del usuario dueño del recibo (auth_user_id SSOT).",
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
    
    # =========================================================================
    # Campos para enlaces públicos (compartir recibo sin login)
    # =========================================================================
    
    public_token: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        unique=True,
        index=True,
        doc="Token URL-safe para acceso público al recibo sin autenticación.",
    )
    
    public_token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Fecha de expiración del token público.",
    )
    
    purchase_email_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp de envío del email de confirmación de compra.",
    )
    
    admin_notify_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp de envío de notificación al admin. Usado para idempotencia.",
    )
    
    __table_args__ = (
        Index("ix_billing_invoices_user_issued", "auth_user_id", "issued_at"),
    )
    
    def __repr__(self) -> str:
        return f"<BillingInvoice id={self.id} number={self.invoice_number} auth_user_id={str(self.auth_user_id)[:8]}...>"
    
    def is_public_token_valid(self) -> bool:
        """Verifica si el token público existe y no ha expirado."""
        if not self.public_token:
            return False
        if not self.public_token_expires_at:
            return True  # Sin expiración = siempre válido
        return datetime.now(self.public_token_expires_at.tzinfo) < self.public_token_expires_at


__all__ = ["BillingInvoice"]
