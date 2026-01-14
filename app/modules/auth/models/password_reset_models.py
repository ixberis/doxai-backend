# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/models/password_reset_models.py

Modelo ORM para reseteo de contraseña.
Alineado con AppUser (tabla app_users) y relaciones correctas.

Incluye campos para tracking de reintentos de email:
- reset_email_status
- reset_email_attempts
- reset_email_claimed_at
- reset_email_sent_at
- reset_email_last_error

Autor: Ixchel Beristain
Fecha: 21/10/2025
Updated: 2025-12-15 - Añadidos campos de email retry
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from uuid import UUID

from sqlalchemy import String, ForeignKey, DateTime, func, Index, Integer, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.database.database import Base

if TYPE_CHECKING:
    # Solo para análisis estático, evita imports circulares en runtime
    from app.modules.auth.models.user_models import AppUser

import enum


class EmailStatusEnum(str, enum.Enum):
    """Estado del envío de email."""
    pending = "pending"
    sent = "sent"
    failed = "failed"


class PasswordReset(Base):
    __tablename__ = "password_resets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # BD 2.0 SSOT: auth_user_id es el identificador principal para RLS/ownership
    auth_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("app_users.auth_user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # FK a AppUser.user_id (tabla app_users) - Compat/referencia interna
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Token único de reset
    token: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)

    # Tiempos base
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Campos de email retry tracking
    reset_email_status: Mapped[str] = mapped_column(
        SQLEnum(EmailStatusEnum, name="email_status_enum", create_type=False),
        nullable=False,
        default=EmailStatusEnum.pending,
        server_default="pending",
    )
    reset_email_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    reset_email_claimed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reset_email_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reset_email_last_error: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )

    # Relación correcta con AppUser
    user: Mapped["AppUser"] = relationship(
        "AppUser",
        back_populates="password_resets",
        foreign_keys=[user_id],
        lazy="joined",
    )

# Índice para expiración (housekeeping)
Index("ix_password_resets_expires_at", PasswordReset.expires_at)

# Índices para retry queries
Index("ix_password_resets_email_status", PasswordReset.reset_email_status)
Index(
    "ix_password_resets_retry_candidates",
    PasswordReset.reset_email_status,
    PasswordReset.reset_email_attempts,
    PasswordReset.expires_at,
)

# NOTA: Token de 128 caracteres con unique=True es apropiado para tokens aleatorios.
# Consistente con AccountActivation para homogeneidad.

# Fin del archivo password_reset_models.py