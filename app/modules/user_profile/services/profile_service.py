
# -*- coding: utf-8 -*-
"""
backend/app/modules/user_profile/services/profile_service.py

Servicio para gestión del perfil de usuario en DoxAI.

Funcionalidades:
1) Perfil de usuario
   - Visualización y edición de datos personales (nombre, teléfono y correo)
   - Cambio de contraseña (verifica la actual, guarda hash de la nueva)

2) Gestión de créditos
   - Visualización de saldo actual
   - Generación de URL para compra de créditos (frontend)

3) Cerrar sesión
   - Revocación/invalidación de sesión mediante SessionManager (inyectable)

Dependencias esperadas (inyectables):
- AsyncSession (SQLAlchemy)
- PasswordHasher: verify(plain, hash) -> bool ; hash(plain) -> str
- SessionManager: revoke_session(user_id: UUID, session_id: str | None) -> None
- CreditsGateway (opcional): get_balance(user_id) -> int ; get_overview(user_id) -> CreditsOverviewDTO

Autor: DoxAI
Fecha: 2025-10-23
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Protocol
from uuid import UUID
from datetime import datetime, timezone

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update, text
from sqlalchemy.ext.asyncio import AsyncSession

# Reutilizamos enums del módulo auth (no crear enums en perfil)
from app.modules.auth.enums import UserRole, UserStatus  # noqa: F401

# Modelo de usuario (ajusta el import si tu path es distinto)
from app.modules.auth.models.user_models import User  # type: ignore


logger = logging.getLogger(__name__)


# ============================
# Protocolos / Gateways
# ============================

class PasswordHasher(Protocol):
    def verify(self, plain_password: str, password_hash: str) -> bool: ...
    def hash(self, plain_password: str) -> str: ...


class SessionManager(Protocol):
    async def revoke_session(self, user_id: UUID, session_id: Optional[str]) -> None: ...


class CreditsGateway(Protocol):
    async def get_balance(self, user_id: UUID) -> int: ...
    async def get_overview(self, user_id: UUID) -> "CreditsOverviewDTO": ...


# ============================
# DTOs
# ============================

class ProfileDTO(BaseModel):
    user_id: UUID
    full_name: str
    email: EmailStr
    phone: Optional[str] = None
    role: str
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_login: Optional[datetime] = None


class UpdateProfileDTO(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1)
    phone: Optional[str] = None
    email: Optional[EmailStr] = None


class ChangePasswordDTO(BaseModel):
    current_password: str = Field(min_length=8)
    new_password: str = Field(min_length=8)


class CreditsOverviewDTO(BaseModel):
    balance: int = 0
    last_top_up_at: Optional[datetime] = None
    last_consume_at: Optional[datetime] = None


class PurchaseCreditsLinkDTO(BaseModel):
    url: str


# ============================
# Servicio
# ============================

@dataclass
class ProfileService:
    db: AsyncSession
    password_hasher: PasswordHasher
    session_manager: SessionManager
    credits_gateway: Optional[CreditsGateway] = None
    # Base del frontend para armar el deep-link de compra de créditos
    frontend_base_url: str = "http://localhost:8080"

    # ---------- Perfil: lectura ----------

    async def get_profile(self, user_id: UUID) -> ProfileDTO:
        stmt = select(User).where(User.user_id == user_id)
        result = await self.db.execute(stmt)
        user: Optional[User] = result.scalar_one_or_none()

        if not user:
            raise ValueError("Usuario no encontrado")

        return ProfileDTO(
            user_id=user.user_id,
            full_name=user.full_name,
            email=user.email,
            phone=getattr(user, "phone", None),
            role=str(getattr(user, "role", "")),
            status=str(getattr(user, "status", "")),
            created_at=user.created_at,
            updated_at=getattr(user, "updated_at", None),
            last_login=getattr(user, "user_last_login", None),
        )

    # ---------- Perfil: edición ----------

    async def update_profile(self, user_id: UUID, data: UpdateProfileDTO) -> ProfileDTO:
        # Si cambia el email, validar unicidad (case-insensitive)
        if data.email is not None:
            stmt_email = select(User).where(User.email.ilike(str(data.email)))
            result_email = await self.db.execute(stmt_email)
            existing = result_email.scalar_one_or_none()
            if existing and existing.user_id != user_id:
                raise ValueError("El correo ya está en uso por otro usuario")

        stmt = select(User).where(User.user_id == user_id)
        result = await self.db.execute(stmt)
        user: Optional[User] = result.scalar_one_or_none()
        if not user:
            raise ValueError("Usuario no encontrado")

        if data.full_name is not None:
            user.full_name = data.full_name.strip()

        if data.phone is not None:
            user.phone = data.phone.strip() if data.phone else None  # permite limpiar a None

        if data.email is not None:
            user.email = str(data.email).lower()

        # Timestamps
        if hasattr(user, "updated_at"):
            user.updated_at = datetime.now(timezone.utc)

        await self.db.flush()
        await self.db.commit()

        return await self.get_profile(user_id)

    # ---------- Cambio de contraseña ----------

    async def change_password(self, user_id: UUID, payload: ChangePasswordDTO) -> None:
        stmt = select(User).where(User.user_id == user_id)
        result = await self.db.execute(stmt)
        user: Optional[User] = result.scalar_one_or_none()
        if not user:
            raise ValueError("Usuario no encontrado")

        password_hash: str = getattr(user, "password_hash", "")
        if not password_hash:
            raise RuntimeError("El usuario no tiene password_hash definido")

        if not self.password_hasher.verify(payload.current_password, password_hash):
            raise ValueError("La contraseña actual no es correcta")

        new_hash = self.password_hasher.hash(payload.new_password)
        user.password_hash = new_hash

        if hasattr(user, "updated_at"):
            user.updated_at = datetime.now(timezone.utc)

        await self.db.flush()
        await self.db.commit()

    # ---------- Créditos: balance y overview ----------

    async def get_credits_balance(self, user_id: UUID) -> int:
        """
        Regresa el saldo actual de créditos.

        Prioridad:
          1) credits_gateway (si está inyectado)
          2) fallback SQL simple sobre 'credit_balances' (si existe)
          3) 0 (sin romper la pantalla)
        """
        # 1) Gateway inyectado
        if self.credits_gateway is not None:
            try:
                return await self.credits_gateway.get_balance(user_id)
            except Exception as e:
                logger.warning(f"[credits_gateway] get_balance falló: {e}")

        # 2) Fallback SQL (tabla opcional)
        try:
            stmt = text(
                "SELECT balance FROM credit_balances WHERE user_id = :uid LIMIT 1"
            )
            res = await self.db.execute(stmt, {"uid": str(user_id)})
            row = res.first()
            if row and row[0] is not None:
                return int(row[0])
        except Exception as e:
            logger.info(f"[fallback] No se pudo leer credit_balances: {e}")

        # 3) Default
        return 0

    async def get_credits_overview(self, user_id: UUID) -> CreditsOverviewDTO:
        """
        Devuelve un overview simple: balance y timestamps de última recarga/consumo.

        Prioridad:
          1) credits_gateway (si está)
          2) Fallback SQL sobre credit_transactions (si existe)
          3) balance=0 sin fechas
        """
        # 1) Gateway inyectado
        if self.credits_gateway is not None:
            try:
                return await self.credits_gateway.get_overview(user_id)
            except Exception as e:
                logger.warning(f"[credits_gateway] get_overview falló: {e}")

        # 2) Fallback SQL
        overview = CreditsOverviewDTO(balance=await self.get_credits_balance(user_id))
        try:
            # Suponiendo tipos 'top_up' y 'consume'
            stmt_last_topup = text(
                """
                SELECT created_at
                FROM credit_transactions
                WHERE user_id = :uid AND type = 'top_up'
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
            res_topup = await self.db.execute(stmt_last_topup, {"uid": str(user_id)})
            row_topup = res_topup.first()
            if row_topup:
                overview.last_top_up_at = row_topup[0]

            stmt_last_consume = text(
                """
                SELECT created_at
                FROM credit_transactions
                WHERE user_id = :uid AND type = 'consume'
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
            res_consume = await self.db.execute(stmt_last_consume, {"uid": str(user_id)})
            row_consume = res_consume.first()
            if row_consume:
                overview.last_consume_at = row_consume[0]

        except Exception as e:
            logger.info(f"[fallback] No se pudo leer credit_transactions: {e}")

        return overview

    # ---------- Créditos: link de compra ----------

    async def get_purchase_credits_link(
        self, user_id: UUID, redirect_path: str = "/dashboard/credits"
    ) -> PurchaseCreditsLinkDTO:
        """
        Devuelve el deep link del frontend para comprar créditos.
        Si usas proveedor externo (Stripe/PayPal), el flujo puede iniciar desde el frontend.

        redirect_path: ruta del frontend a la que volver tras el pago.
        """
        # En apps productivas, podrías firmar un state param JWT con user_id para volver con seguridad.
        url = f"{self.frontend_base_url.rstrip('/')}/billing/credits?redirect={redirect_path}"
        return PurchaseCreditsLinkDTO(url=url)

    # ---------- Cerrar sesión ----------

    async def logout(self, user_id: UUID, session_id: Optional[str]) -> None:
        """
        Revoca la sesión actual del usuario. La implementación real depende
        del SessionManager inyectado (Redis, tabla refresh_tokens, etc.).
        """
        try:
            await self.session_manager.revoke_session(user_id, session_id)
        except Exception as e:
            logger.error(f"No se pudo revocar la sesión: {e}")
            # A discreción: no levantar para no bloquear UI. Aquí optamos por propagar.
            raise


# Alias para compatibilidad con otros módulos
UserProfileService = ProfileService

# Fin del archivo