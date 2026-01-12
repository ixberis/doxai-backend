# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/credits/models.py

Modelos ORM para el sistema de créditos.

Sincronizados con BD 2.0:
- database/common/01_extensions_and_functions/10_wallets.sql (public.wallets)
- database/payments/02_tables/04_credit_transactions.sql
- database/payments/02_tables/05_usage_reservations.sql

Autor: DoxAI
Fecha: 2025-12-30
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Integer,
    Text,
    DateTime,
    Enum as SQLEnum,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.base import Base
from .enums import CreditTxType, ReservationStatus


class Wallet(Base):
    """
    Saldo de créditos del usuario (denormalizado para lectura rápida).

    Tabla: public.wallets (BD 2.0)
    """

    __tablename__ = "wallets"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    auth_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        unique=True,
        index=True,
    )

    # BD 2.0 SSOT: user_id legacy eliminado, solo auth_user_id

    balance: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    balance_reserved: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
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

    @property
    def available(self) -> int:
        """Créditos disponibles (balance - reserved)."""
        return self.balance - self.balance_reserved

    def __repr__(self) -> str:
        return (
            f"<Wallet id={self.id} auth_user_id={str(self.auth_user_id)[:8]}... "
            f"balance={self.balance} reserved={self.balance_reserved}>"
        )


class CreditTransaction(Base):
    """
    Ledger inmutable de movimientos de créditos.

    Tabla: public.credit_transactions
    """

    __tablename__ = "credit_transactions"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    auth_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # BD 2.0 SSOT: user_id legacy eliminado, solo auth_user_id

    payment_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
    )

    reservation_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
    )

    tx_type: Mapped[CreditTxType] = mapped_column(
        SQLEnum(
            CreditTxType,
            name="credit_tx_type_enum",
            create_type=False,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )

    credits_delta: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    balance_after: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    operation_code: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    job_id: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    idempotency_key: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    tx_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="'{}'::jsonb",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<CreditTransaction id={self.id} auth_user_id={str(self.auth_user_id)[:8]}... "
            f"delta={self.credits_delta:+d} after={self.balance_after}>"
        )


class UsageReservation(Base):
    """
    Reservación de créditos para operaciones de uso (e.g., pipelines RAG).

    Tabla: public.usage_reservations
    """

    __tablename__ = "usage_reservations"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    auth_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # BD 2.0 SSOT: user_id legacy eliminado, solo auth_user_id

    credits_reserved: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    credits_consumed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    job_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
    )

    operation_code: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    reservation_status: Mapped[ReservationStatus] = mapped_column(
        SQLEnum(
            ReservationStatus,
            name="reservation_status_enum",
            create_type=False,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )

    idempotency_key: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    reservation_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    consumed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    released_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    expired_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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

    def __repr__(self) -> str:
        return (
            f"<UsageReservation id={self.id} auth_user_id={str(self.auth_user_id)[:8]}... "
            f"reserved={self.credits_reserved} status={self.reservation_status}>"
        )


__all__ = [
    "Wallet",
    "CreditTransaction",
    "UsageReservation",
]
