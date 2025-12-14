# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/models/login_models.py

Modelos ORM para auditoría de login y gestión de sesiones.
Alineado con AppUser (tabla app_users) y usando enums del módulo auth.

Autor: Ixchel Beristain
Fecha: 25/10/2025
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Boolean, ForeignKey, DateTime, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.database.database import Base
from app.modules.auth.enums import LoginFailureReason, login_failure_reason_pg_enum
from app.modules.auth.enums import TokenType, token_type_pg_enum

if TYPE_CHECKING:
    from app.modules.auth.models.user_models import AppUser


class LoginAttempt(Base):
    """
    Registro de auditoría de intentos de login (éxito y fallo).
    """
    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # FK a AppUser.user_id
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Resultado del intento
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    
    # Razón de falla (si success=False)
    reason: Mapped[Optional[LoginFailureReason]] = mapped_column(
        login_failure_reason_pg_enum(create_type=False),
        nullable=True,
    )

    # Auditoría
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)  # IPv6
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relación con AppUser
    user: Mapped["AppUser"] = relationship(
        "AppUser",
        back_populates="login_attempts",
        foreign_keys=[user_id],
        lazy="joined",
    )


class UserSession(Base):
    """
    Gestión de sesiones activas y tokens (access/refresh).
    """
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # FK a AppUser.user_id
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Tipo de token
    token_type: Mapped[TokenType] = mapped_column(
        token_type_pg_enum(create_type=False),
        nullable=False,
        server_default=TokenType.access.value,
    )

    # Hash del token (no el token en claro)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)

    # Tiempos de vigencia
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Auditoría opcional
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Relación con AppUser
    user: Mapped["AppUser"] = relationship(
        "AppUser",
        back_populates="sessions",
        foreign_keys=[user_id],
        lazy="joined",
    )


# Índices compuestos para consultas comunes
Index("ix_login_attempts_user_created", LoginAttempt.user_id, LoginAttempt.created_at)
Index("ix_user_sessions_user_expires", UserSession.user_id, UserSession.expires_at)

__all__ = ["LoginAttempt", "UserSession"]

# Fin del archivo backend/app/modules/auth/models/login_models.py
