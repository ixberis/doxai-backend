
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/models/activation_models.py

Modelo ORM para el flujo de activación de cuenta.
Alineado con AppUser (tabla app_users) y relaciones bidireccionales correctas.

Autor: Ixchel Beristain
Fecha: 21/10/2025
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, ForeignKey, DateTime, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.database.database import Base
from app.modules.auth.enums import ActivationStatus, activation_status_pg_enum

if TYPE_CHECKING:
    # Solo para análisis estático (Pylance), evita import circular en runtime
    from app.modules.auth.models.user_models import AppUser

# NOTA: Los enums se crean vía Alembic (create_type=False).
# Para bootstrap sin migraciones, pasar explícitamente create_type=True.


class AccountActivation(Base):
    __tablename__ = "account_activations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # FK a AppUser.user_id (tabla app_users)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Token de activación único
    token: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)

    # Estado explícito usando enum
    status: Mapped[ActivationStatus] = mapped_column(
        activation_status_pg_enum(create_type=False),
        nullable=False,
        server_default=ActivationStatus.sent.value
    )

    # Tiempos
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relación correcta: con la clase "AppUser"
    user: Mapped["AppUser"] = relationship(
        "AppUser",
        back_populates="account_activations",
        foreign_keys=[user_id],
        lazy="joined",
    )

# Índice para expiración (housekeeping)
Index("ix_account_activations_expires_at", AccountActivation.expires_at)

# NOTA: Índice parcial opcional para optimizar consultas de "pendientes":
# Cuando adoptes migraciones con Alembic, considera añadir:
# CREATE INDEX ix_account_activations_pending 
#   ON account_activations (user_id, expires_at)
#   WHERE status = 'sent' AND consumed_at IS NULL;

# Fin del archivo activation_models.py