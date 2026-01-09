# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/models/user_models.py

Modelo principal de usuarios (AppUser).

IMPORTANTE - RESOLUCIÓN DE RELATIONSHIPS:
SQLAlchemy resuelve relationships con strings ("ClassName") buscando en el
mapper registry. Para que esto funcione, las clases referenciadas DEBEN estar
importadas y registradas ANTES de que configure_mappers() se ejecute.

Este módulo importa explícitamente los modelos hijos (AccountActivation,
LoginAttempt, etc.) para garantizar que estén registrados cuando se importe
AppUser directamente (no solo vía el barrel __init__.py).

Autor: Ixchel Beristáin
Fecha: 18/10/2025
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from uuid import UUID as PyUUID
from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.shared.database.database import Base
from app.modules.auth.enums import UserRole, user_role_pg_enum
from app.modules.auth.enums import UserStatus, user_status_pg_enum

# ═══════════════════════════════════════════════════════════════════════════════
# IMPORTS OBLIGATORIOS PARA RESOLVER RELATIONSHIPS
# ═══════════════════════════════════════════════════════════════════════════════
# Estos imports aseguran que los modelos hijos estén registrados en el mapper
# registry de SQLAlchemy ANTES de que AppUser intente resolver sus relationships.
# Sin estos imports, "LoginAttempt" y otros strings no se resuelven si alguien
# importa AppUser directamente (from .user_models import AppUser).
# ═══════════════════════════════════════════════════════════════════════════════
from app.modules.auth.models.activation_models import AccountActivation  # noqa: F401
from app.modules.auth.models.password_reset_models import PasswordReset  # noqa: F401
from app.modules.auth.models.login_models import LoginAttempt, UserSession  # noqa: F401

# NOTA: Las relaciones cross-module (payments, wallet, credit_transactions,
# usage_reservations) se registran en app/shared/orm/cross_module_relationships.py
# para evitar dependencias circulares y permitir que el módulo auth ejecute
# configure_mappers() de forma aislada.


class AppUser(Base):
    __tablename__ = "app_users"

    # PK interna (INT) - SOLO para administración/reportes internos
    user_id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # SSOT: auth_user_id (UUID) - IDENTIDAD GLOBAL DEL USUARIO EN DOXAI
    # ═══════════════════════════════════════════════════════════════════════════
    # - NO tiene server_default: el backend DEBE generarlo con uuid4() al registrar
    # - NOT NULL para instalación limpia (nullable=False)
    # - UNIQUE: permite lookup eficiente por UUID
    # - Este UUID va en JWT sub y se usa para ownership en: projects, rag, billing
    # - NO existe "auth.users" como SSOT externa; app_users.auth_user_id ES el SSOT
    # ═══════════════════════════════════════════════════════════════════════════
    auth_user_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True), 
        unique=True, 
        nullable=False,  # NOT NULL - obligatorio
        index=True,
        # NO server_default - se genera en el backend con uuid4()
    )
    
    user_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    user_email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    user_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    user_password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    user_role: Mapped[UserRole] = mapped_column(
        user_role_pg_enum(create_type=False),
        nullable=False,
        server_default="customer",
    )
    user_status: Mapped[UserStatus] = mapped_column(
        user_status_pg_enum(create_type=False),
        nullable=False,
        server_default="active",
    )

    user_is_activated: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    user_activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    user_last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Welcome email tracking (estado explícito + claim atómico)
    welcome_email_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    welcome_email_claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    welcome_email_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    welcome_email_last_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    welcome_email_attempts: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
    
    user_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    user_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # --- Auth relationships (strings simples, el __init__.py garantiza el orden correcto) ---
    account_activations: Mapped[List["AccountActivation"]] = relationship(
        "AccountActivation", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    password_resets: Mapped[List["PasswordReset"]] = relationship(
        "PasswordReset", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    login_attempts: Mapped[List["LoginAttempt"]] = relationship(
        "LoginAttempt", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    sessions: Mapped[List["UserSession"]] = relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    # NOTA: Las relaciones payments, wallet, credit_transactions, usage_reservations
    # se registran dinámicamente en app/shared/orm/cross_module_relationships.py
    # para evitar dependencias con el módulo payments durante configure_mappers().

    def __repr__(self) -> str:
        return f"<AppUser user_id={self.user_id} email={self.user_email!r} active={self.user_is_activated}>"

User = AppUser
__all__ = ["AppUser", "User"]
# Fin del archivo