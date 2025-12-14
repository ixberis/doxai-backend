
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/models/credit_transaction_models.py

Modelo ORM v3.0 para credit_transactions,
alineado al SQL oficial del ledger.

Autor: Ixchel Beristain
Fecha: 2025-11-21
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import BigInteger, Integer, Text, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.database.base import Base
from app.modules.payments.enums import CreditTxType

if TYPE_CHECKING:
    from app.modules.auth.models.user_models import AppUser


class CreditTransaction(Base):
    """
    Ledger inmutable de créditos por usuario.

    Cada fila representa un movimiento:
    - user_id        → usuario dueño de la transacción
    - credits_delta  → +N abono, -N cargo
    - balance_after  → saldo después de aplicar la transacción
    """

    __tablename__ = "credit_transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # FK principal al usuario (según SQL: BIGINT NOT NULL)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("app_users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    payment_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reservation_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("usage_reservations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    tx_type: Mapped[CreditTxType] = mapped_column(
        CreditTxType.as_pg_enum(),
        nullable=False,
    )
    credits_delta: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="+N abono, -N cargo",
    )
    balance_after: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Saldo del usuario después de aplicar esta transacción.",
    )

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    operation_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True)
    job_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 👇 nombre de atributo distinto, columna sigue siendo "metadata"
    metadata_json: Mapped[dict] = mapped_column(
        "metadata",           # nombre de columna real
        JSONB,
        nullable=False,
        default=dict,
        doc="Metadatos JSON de la transacción.",
    )

    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )

    # Restricciones
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            "operation_code",
            name="uq_credit_tx_idempotency",
        ),
    )

    # Relaciones
    user: Mapped["AppUser"] = relationship(
        "AppUser",
        back_populates="credit_transactions",
        lazy="noload",
    )

    def __repr__(self) -> str:  # pragma: no cover - representacional
        return (
            f"<CreditTransaction id={self.id} user_id={self.user_id} "
            f"delta={self.credits_delta} balance_after={self.balance_after}>"
        )

# Fin del archivo backend\app\modules\payments\models\credit_transaction_models.py
