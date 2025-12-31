# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/credits/models.py

Modelos ORM para el sistema de créditos.

Sincronizados con:
- database/payments/02_tables/01_wallets.sql (payments_wallet / wallets view)
- database/payments/02_tables/04_credit_transactions.sql
- database/payments/02_tables/05_usage_reservations.sql

Autor: DoxAI
Fecha: 2025-12-30
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Any

from sqlalchemy import (
    BigInteger,
    Integer,
    Text,
    DateTime,
    Enum as SQLEnum,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.base import Base
from .enums import CreditTxType, ReservationStatus


class Wallet(Base):
    """
    Saldo de créditos del usuario (denormalizado para lectura rápida).
    
    Tabla: public.payments_wallet
    
    Columnas DB:
    - id: BIGSERIAL PRIMARY KEY
    - user_id: BIGINT NOT NULL UNIQUE
    - balance: INTEGER NOT NULL DEFAULT 0
    - balance_reserved: INTEGER NOT NULL DEFAULT 0
    - created_at: TIMESTAMPTZ NOT NULL DEFAULT now()
    - updated_at: TIMESTAMPTZ NOT NULL DEFAULT now()
    
    Constraints:
    - ck_wallet_non_negative: balance >= 0 AND balance_reserved >= 0
    - ck_wallet_reserved_le_balance: balance_reserved <= balance
    """
    
    __tablename__ = "payments_wallet"
    
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        unique=True,
        index=True,
    )
    
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
    
    # Constraints definidos en DB, no duplicar aquí para evitar conflictos
    # Los constraints ck_wallet_non_negative y ck_wallet_reserved_le_balance
    # ya existen en la tabla
    
    @property
    def available(self) -> int:
        """Créditos disponibles (balance - reserved)."""
        return self.balance - self.balance_reserved
    
    def __repr__(self) -> str:
        return f"<Wallet id={self.id} user={self.user_id} balance={self.balance} reserved={self.balance_reserved}>"


class CreditTransaction(Base):
    """
    Ledger inmutable de movimientos de créditos.
    
    Tabla: public.credit_transactions
    
    Columnas DB:
    - id: BIGSERIAL PRIMARY KEY
    - user_id: BIGINT NOT NULL
    - payment_id: BIGINT (nullable)
    - reservation_id: BIGINT (nullable)
    - tx_type: credit_tx_type_enum NOT NULL ('credit' | 'debit')
    - credits_delta: INTEGER NOT NULL
    - balance_after: INTEGER NOT NULL
    - description: TEXT (nullable)
    - operation_code: TEXT (nullable)
    - job_id: TEXT (nullable)
    - idempotency_key: TEXT (nullable)
    - metadata: JSONB NOT NULL DEFAULT '{}'
    - created_at: TIMESTAMPTZ NOT NULL DEFAULT now()
    
    Constraints:
    - uq_credit_tx_user_idem: UNIQUE(user_id, idempotency_key)
    - ck_credit_tx_nonzero: credits_delta <> 0
    - uq_credit_tx_reservation_debit: UNIQUE(reservation_id) WHERE tx_type='debit'
    """
    
    __tablename__ = "credit_transactions"
    
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )
    
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
    
    # Renombrar atributo a tx_metadata para evitar conflicto con SQLAlchemy
    # pero mapear a la columna real "metadata"
    tx_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",  # nombre real de la columna en DB
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
    
    # No declarar __table_args__ con índices/constraints que ya existen en DB
    # Evita conflictos si se usa create_all en tests
    # Los índices ix_credit_tx_user_created, ix_credit_tx_payment ya existen en SQL
    
    def __repr__(self) -> str:
        return f"<CreditTransaction id={self.id} user={self.user_id} delta={self.credits_delta:+d} after={self.balance_after}>"


class UsageReservation(Base):
    """
    Reservación de créditos para operaciones de uso (e.g., pipelines RAG).
    
    Tabla: public.usage_reservations
    
    Columnas DB:
    - id: BIGSERIAL PRIMARY KEY
    - user_id: BIGINT NOT NULL
    - credits_reserved: INTEGER NOT NULL
    - credits_consumed: INTEGER NOT NULL DEFAULT 0
    - job_id: BIGINT (nullable)
    - operation_code: TEXT (nullable)
    - reservation_status: reservation_status_enum NOT NULL
    - idempotency_key: TEXT (nullable)
    - reason: TEXT (nullable)
    - reservation_expires_at: TIMESTAMPTZ (nullable)
    - consumed_at: TIMESTAMPTZ (nullable)
    - released_at: TIMESTAMPTZ (nullable)
    - expired_at: TIMESTAMPTZ (nullable)
    - created_at: TIMESTAMPTZ NOT NULL DEFAULT now()
    - updated_at: TIMESTAMPTZ NOT NULL DEFAULT now()
    
    Constraints:
    - uq_usage_reservation_user_idem: UNIQUE(user_id, operation_code, job_id, idempotency_key)
    """
    
    __tablename__ = "usage_reservations"
    
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )
    
    credits_reserved: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    
    credits_consumed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    
    # job_id es BIGINT en DB, no TEXT
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
        return f"<UsageReservation id={self.id} user={self.user_id} reserved={self.credits_reserved} status={self.reservation_status}>"


__all__ = [
    "Wallet",
    "CreditTransaction",
    "UsageReservation",
]
