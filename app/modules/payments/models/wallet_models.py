
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/models/wallet_models.py

Modelo ORM para la tabla wallets (vista sobre payments_wallet).

Reglas de negocio:
- Una wallet por usuario (UNIQUE user_id).
- El balance real se calcula a partir del ledger
  (credit_transactions.credits_delta).
- balance_reserved representa créditos bloqueados por reservas activas.

Autor: Ixchel Beristain
Fecha: 2025-11-20 (ajustado 2025-11-21)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Integer, BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.database.base import Base

if TYPE_CHECKING:
    from app.modules.auth.models.user_models import AppUser


class Wallet(Base):
    """Billetera de un usuario para manejo de créditos."""

    __tablename__ = "wallets"

    # ------------------------------------------------------------------ #
    # Columnas principales (alineadas con SQL: payments_wallet)
    # ------------------------------------------------------------------ #
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)

    # FK a app_users.user_id (BIGSERIAL/BIGINT)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("app_users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="ID del usuario (app_users.user_id) dueño de esta billetera.",
    )

    # Balance total (denormalizado desde ledger)
    balance: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        doc="Balance total de créditos (denormalizado desde ledger).",
    )

    balance_reserved: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        doc="Créditos reservados (bloqueados) por operaciones en curso.",
    )

    # ------------------------------------------------------------------ #
    # Relaciones - usar noload para evitar carga automática
    # ------------------------------------------------------------------ #
    # Relación con AppUser (back_populates se configura en el bootstrap ORM)
    user: Mapped["AppUser"] = relationship(
        "AppUser",
        foreign_keys=[user_id],
        lazy="noload",
        doc="Usuario dueño de esta wallet.",
    )

    # ------------------------------------------------------------------ #
    # Constraints
    # ------------------------------------------------------------------ #
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_wallets_user_id"),
    )

    # ------------------------------------------------------------------ #
    # Métodos auxiliares
    # ------------------------------------------------------------------ #
    def __repr__(self) -> str:  # pragma: no cover - representacional
        return f"<Wallet id={self.id} user_id={self.user_id} balance={self.balance}>"

    def available_credits(self) -> int:
        """Créditos disponibles = balance - balance_reserved."""
        return (self.balance or 0) - (self.balance_reserved or 0)


# Alias legacy para compatibilidad con Auth/tests:
CreditWallet = Wallet  # type: ignore

__all__ = ["Wallet", "CreditWallet"]

# Fin del archivo backend/app/modules/payments/models/wallet_models.py
