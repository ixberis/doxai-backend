
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/models/activation_models.py

Modelo ORM para el flujo de activación de cuenta.
Alineado con AppUser (tabla app_users) y relaciones bidireccionales correctas.

Incluye tracking de envío de email de activación:
- activation_email_status: pending/sent/failed (reusa email_status_enum)
- activation_email_attempts: contador de intentos
- activation_email_sent_at: timestamp de envío exitoso
- activation_email_last_error: último error de envío

Autor: Ixchel Beristain
Fecha: 21/10/2025
Updated: 2025-12-26 - Añadido tracking de email
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, ForeignKey, DateTime, Integer, Text, func, Index
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.database.database import Base
from app.modules.auth.enums import ActivationStatus, activation_status_pg_enum

if TYPE_CHECKING:
    # Solo para análisis estático (Pylance), evita import circular en runtime
    from app.modules.auth.models.user_models import AppUser


# -----------------------------------------------------------------------------
# Reuse existing email_status_enum from DB (same as password_resets)
# Values: 'pending', 'sent', 'failed'
# -----------------------------------------------------------------------------

# Create PG_ENUM reference for email_status_enum (already exists in DB)
email_status_pg_enum = PG_ENUM(
    'pending', 'sent', 'failed',
    name='email_status_enum',
    create_type=False,  # IMPORTANT: enum already exists in DB
)


# NOTA: Los enums se crean vía SQL canónico en database/auth/01_types/.
# Aquí solo los referenciamos con create_type=False.


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

    # Estado del token (sent, used, expired, revoked)
    status: Mapped[ActivationStatus] = mapped_column(
        activation_status_pg_enum(create_type=False),
        nullable=False,
        server_default=ActivationStatus.sent.value
    )

    # Tiempos del token
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # -------------------------------------------------------------------------
    # Tracking de envío de email de activación
    # Reusa email_status_enum existente (pending, sent, failed)
    # -------------------------------------------------------------------------
    activation_email_status: Mapped[str] = mapped_column(
        email_status_pg_enum,
        nullable=False,
        server_default='pending',
        comment="Estado del envío del email de activación"
    )
    
    activation_email_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Número de intentos de envío del email"
    )
    
    activation_email_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp del envío exitoso del email"
    )
    
    activation_email_last_error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Último error al intentar enviar el email"
    )

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


__all__ = [
    "AccountActivation",
    "email_status_pg_enum",
]

# Fin del archivo activation_models.py