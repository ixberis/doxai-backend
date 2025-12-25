
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/models/usage_reservation_models.py

Modelo ORM para reservas de créditos.

Cada reserva:
- Bloquea temporalmente créditos de un usuario
- Se consume, expira o cancela mediante funciones de negocio.

Autor: Ixchel Beristain
Fecha: 2025-11-20
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    String,
    Text,
    Integer,
    BigInteger,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.database.base import Base
from app.modules.payments.enums import ReservationStatus

if TYPE_CHECKING:
    from app.modules.auth.models.user_models import AppUser


class UsageReservation(Base):
    __tablename__ = "usage_reservations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # FK al usuario
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("app_users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Usuario propietario de esta reserva.",
    )

    # Créditos reservados y consumidos
    credits_reserved: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Créditos temporalmente bloqueados por esta reserva.",
    )

    credits_consumed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        doc="Créditos efectivamente consumidos.",
    )

    # Job asociado (opcional)
    job_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        doc="Job asociado (p.ej. RAG pipeline job).",
    )

    # Código de operación (idempotencia)
    operation_code: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        index=True,
        doc="Código lógico de la operación (RAG_PIPELINE, etc.).",
    )

    # Estado de la reservación
    reservation_status: Mapped[ReservationStatus] = mapped_column(
        ReservationStatus.as_pg_enum(),
        nullable=False,
        index=True,
        doc="Estado de la reservación.",
    )

    # Clave de idempotencia
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Clave de idempotencia para evitar reservas duplicadas.",
    )

    # Motivo de la reservación
    reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Motivo legible de la reservación.",
    )

    # Timestamps
    reservation_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Fecha/hora en que expira esta reserva si no se consume.",
    )

    consumed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Fecha/hora en que se consumió la reserva.",
    )

    released_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Fecha/hora en que se liberó la reserva.",
    )

    expired_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Fecha/hora en que expiró la reserva.",
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

    # Relaciones (back_populates con AppUser se configura en el bootstrap ORM)
    user: Mapped["AppUser"] = relationship(
        "AppUser",
        foreign_keys=[user_id],
        lazy="noload",
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "operation_code",
            "job_id",
            "idempotency_key",
            name="uq_usage_reservation_user_idem",
        ),
        Index(
            "ix_usage_reservations_user_status",
            "user_id",
            "reservation_status",
        ),
    )

    # Propiedades de compatibilidad para código que use nombres antiguos
    @property
    def status(self) -> ReservationStatus:
        """Alias para compatibilidad."""
        return self.reservation_status

    @property
    def operation_id(self) -> Optional[str]:
        """Alias para compatibilidad."""
        return self.operation_code

    @property
    def expires_at(self) -> Optional[datetime]:
        """Alias para compatibilidad."""
        return self.reservation_expires_at

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<UsageReservation id={self.id} user_id={self.user_id} "
            f"status={self.reservation_status} credits={self.credits_reserved}>"
        )


# Fin del archivo
