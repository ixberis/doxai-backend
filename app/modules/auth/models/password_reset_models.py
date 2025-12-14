# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/models/password_reset_models.py

Modelo ORM para reseteo de contraseña.
Alineado con AppUser (tabla app_users) y relaciones correctas.

Autor: Ixchel Beristain
Fecha: 21/10/2025
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, ForeignKey, DateTime, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.database.database import Base

if TYPE_CHECKING:
    # Solo para análisis estático, evita imports circulares en runtime
    from app.modules.auth.models.user_models import AppUser


class PasswordReset(Base):
    __tablename__ = "password_resets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # FK a AppUser.user_id (tabla app_users)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Token único de reset
    token: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)

    # Tiempos
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relación correcta con AppUser
    user: Mapped["AppUser"] = relationship(
        "AppUser",
        back_populates="password_resets",
        foreign_keys=[user_id],
        lazy="joined",
    )

# Índice para expiración (housekeeping)
Index("ix_password_resets_expires_at", PasswordReset.expires_at)

# NOTA: Token de 128 caracteres con unique=True es apropiado para tokens aleatorios.
# Consistente con AccountActivation para homogeneidad.

# Fin del archivo password_reset_models.py