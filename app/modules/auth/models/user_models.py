
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/models/user_models.py
Ajustado: relaciones hacia Payments resueltas con callables (no strings).
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.database.database import Base
from app.modules.auth.enums import UserRole, user_role_pg_enum
from app.modules.auth.enums import UserStatus, user_status_pg_enum

if TYPE_CHECKING:
    from app.modules.auth.models.activation_models import AccountActivation
    from app.modules.auth.models.password_reset_models import PasswordReset
    from app.modules.auth.models.login_models import LoginAttempt, UserSession
    from app.modules.payments.models.payment_models import Payment
    from app.modules.payments.models.wallet_models import CreditWallet
    from app.modules.payments.models.credit_transaction_models import CreditTransaction
    from app.modules.payments.models.usage_reservation_models import UsageReservation


class AppUser(Base):
    __tablename__ = "app_users"

    user_id: Mapped[int] = mapped_column(primary_key=True, index=True)
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
    user_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    user_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # --- Auth relationships ---
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

    # --- Payments relationships (callables diferidos, NO strings) ---
    payments: Mapped[List["Payment"]] = relationship(
        lambda: __import__("app.modules.payments.models.payment_models", fromlist=["Payment"]).Payment,
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    wallet: Mapped[Optional["CreditWallet"]] = relationship(
        lambda: __import__("app.modules.payments.models.wallet_models", fromlist=["CreditWallet"]).CreditWallet,
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    credit_transactions: Mapped[List["CreditTransaction"]] = relationship(
        "CreditTransaction",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    usage_reservations: Mapped[List["UsageReservation"]] = relationship(
        lambda: __import__("app.modules.payments.models.usage_reservation_models", fromlist=["UsageReservation"]).UsageReservation,
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<AppUser user_id={self.user_id} email={self.user_email!r} active={self.user_is_activated}>"

User = AppUser
__all__ = ["AppUser", "User"]
# Fin del archivo