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
    async def revoke_session(self, user_id: int, session_id: Optional[str]) -> None: ...


class CreditsGateway(Protocol):
    async def get_balance(self, user_id: int) -> int: ...
    async def get_overview(self, user_id: int) -> "CreditsOverviewDTO": ...


# ============================
# DTOs
# ============================

class ProfileDTO(BaseModel):
    user_id: int  # AppUser.user_id is int, not UUID
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

    async def get_profile(self, user_id: int) -> ProfileDTO:
        """
        Obtiene el perfil de un usuario por su user_id (int).
        """
        import time
        start = time.perf_counter()

        # Seleccionar solo columnas necesarias (evita cargar todo el modelo)
        stmt = select(
            User.user_id,
            User.user_full_name,
            User.user_email,
            User.user_phone,
            User.user_role,
            User.user_status,
            User.user_created_at,
            User.user_updated_at,
            User.user_last_login,
        ).where(User.user_id == user_id)

        result = await self.db.execute(stmt)
        row = result.first()

        duration_ms = (time.perf_counter() - start) * 1000
        if duration_ms > 500:
            logger.warning(f"query_slow operation=get_profile user_id={user_id} duration_ms={duration_ms:.2f}")
        else:
            logger.debug(f"query_completed operation=get_profile user_id={user_id} duration_ms={duration_ms:.2f}")

        if not row:
            raise ValueError("Usuario no encontrado")

        return ProfileDTO(
            user_id=row[0],
            full_name=row[1],
            email=row[2],
            phone=row[3],
            role=str(row[4].value) if hasattr(row[4], "value") else str(row[4]),
            status=str(row[5].value) if hasattr(row[5], "value") else str(row[5]),
            created_at=row[6],
            updated_at=row[7],
            last_login=row[8],
        )

    # ---------- Perfil: edición ----------

    async def update_profile(self, user_id: int, data: UpdateProfileDTO) -> ProfileDTO:
        """
        Actualiza el perfil de un usuario.
        """
        # Si cambia el email, validar unicidad (case-insensitive)
        if data.email is not None:
            stmt_email = select(User).where(User.user_email.ilike(str(data.email)))
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
            user.user_full_name = data.full_name.strip()

        if data.phone is not None:
            user.user_phone = data.phone.strip() if data.phone else None

        if data.email is not None:
            user.user_email = str(data.email).lower()

        await self.db.flush()
        await self.db.commit()

        return await self.get_profile(user_id)

    # ---------- Cambio de contraseña ----------

    async def change_password(self, user_id: int, payload: ChangePasswordDTO) -> None:
        """
        Cambia la contraseña del usuario.
        """
        stmt = select(User).where(User.user_id == user_id)
        result = await self.db.execute(stmt)
        user: Optional[User] = result.scalar_one_or_none()
        if not user:
            raise ValueError("Usuario no encontrado")

        password_hash: str = user.user_password_hash or ""
        if not password_hash:
            raise RuntimeError("El usuario no tiene password_hash definido")

        if not self.password_hasher.verify(payload.current_password, password_hash):
            raise ValueError("La contraseña actual no es correcta")

        new_hash = self.password_hasher.hash(payload.new_password)
        user.user_password_hash = new_hash

        await self.db.flush()
        await self.db.commit()

    # ---------- Créditos: balance y overview ----------

    async def get_credits_balance(self, user_id: int) -> int:
        """
        Regresa el saldo actual de créditos.

        Prioridad:
          1) credits_gateway (si está inyectado)
          2) Wallet denormalizada (BD 2.0): public.wallets.balance (lookup 1 fila)
          3) Ledger credit_transactions (suma credits_delta) - fallback
          4) 0 (best-effort)

        IMPORTANTE:
        - Cada fallback hace rollback en caso de error para evitar que el
          request quede en estado "transaction aborted" (InFailedSQLTransactionError).
        """
        import time
        start = time.perf_counter()

        # 1) Gateway inyectado
        if self.credits_gateway is not None:
            try:
                balance = await self.credits_gateway.get_balance(user_id)
                duration_ms = (time.perf_counter() - start) * 1000
                logger.debug(f"[credits] user_id={user_id} balance={balance} source=gateway duration_ms={duration_ms:.2f}")
                return int(balance)
            except Exception as e:
                logger.warning(f"[credits_gateway] get_balance falló: {e}")

        # 2) Wallet denormalizada (BD 2.0): wallets
        try:
            stmt = text("SELECT balance FROM wallets WHERE user_id = :uid")
            res = await self.db.execute(stmt, {"uid": user_id})
            row = res.first()
            if row and row[0] is not None:
                balance = int(row[0])
                duration_ms = (time.perf_counter() - start) * 1000
                if duration_ms > 500:
                    logger.warning(f"query_slow operation=get_credits_balance user_id={user_id} duration_ms={duration_ms:.2f}")
                else:
                    logger.debug(f"[credits] user_id={user_id} balance={balance} source=wallets duration_ms={duration_ms:.2f}")
                return balance
        except Exception as e:
            # Rollback para no envenenar la transacción del request
            try:
                await self.db.rollback()
            except Exception:
                pass
            logger.debug(f"[credits] Wallet (wallets) no disponible, fallback a ledger: {e}")

        # 3) Ledger SQL: suma de credit_transactions.credits_delta (fallback)
        try:
            stmt = text("SELECT COALESCE(SUM(credits_delta), 0) FROM credit_transactions WHERE user_id = :uid")
            res = await self.db.execute(stmt, {"uid": user_id})
            row = res.first()
            if row and row[0] is not None:
                balance = int(row[0])
                duration_ms = (time.perf_counter() - start) * 1000
                if duration_ms > 500:
                    logger.warning(f"query_slow operation=get_credits_balance user_id={user_id} duration_ms={duration_ms:.2f}")
                else:
                    logger.debug(f"[credits] user_id={user_id} balance={balance} source=ledger duration_ms={duration_ms:.2f}")
                return balance
        except Exception as e:
            try:
                await self.db.rollback()
            except Exception:
                pass
            logger.info(f"[credits] No se pudo leer credit_transactions: {e}")

        # 4) Default best-effort (sin datos, sin error)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.debug(f"[credits] user_id={user_id} balance=0 source=fallback_zero duration_ms={duration_ms:.2f}")
        return 0

    async def get_credits_overview(self, user_id: int) -> CreditsOverviewDTO:
        """
        Devuelve un overview simple: balance y timestamps de última recarga/consumo.

        Prioridad:
          1) credits_gateway (si está)
          2) Fallback SQL sobre credit_transactions (best-effort)
          3) balance=0 sin fechas

        Nota:
        - Este fallback intenta ser tolerante: si no hay columnas esperadas,
          no rompe el endpoint.
        - Si falla un query, hace rollback para no envenenar la transacción.
        """
        # 1) Gateway inyectado
        if self.credits_gateway is not None:
            try:
                return await self.credits_gateway.get_overview(user_id)
            except Exception as e:
                logger.warning(f"[credits_gateway] get_overview falló: {e}")

        overview = CreditsOverviewDTO(balance=await self.get_credits_balance(user_id))

        # 2) Fallback SQL (best-effort)
        try:
            # Heurística: usamos operation_code por compatibilidad común
            # (SIGNUP_BONUS, TOP_UP, CONSUME, etc.). Si tu esquema difiere, no rompe.
            stmt_last_topup = text(
                """
                SELECT created_at
                FROM credit_transactions
                WHERE user_id = :uid AND (operation_code = 'SIGNUP_BONUS' OR operation_code ILIKE '%TOP%')
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
            res_topup = await self.db.execute(stmt_last_topup, {"uid": user_id})
            row_topup = res_topup.first()
            if row_topup:
                overview.last_top_up_at = row_topup[0]

            stmt_last_consume = text(
                """
                SELECT created_at
                FROM credit_transactions
                WHERE user_id = :uid AND operation_code ILIKE '%CONSUM%'
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
            res_consume = await self.db.execute(stmt_last_consume, {"uid": user_id})
            row_consume = res_consume.first()
            if row_consume:
                overview.last_consume_at = row_consume[0]

        except Exception as e:
            try:
                await self.db.rollback()
            except Exception:
                pass
            logger.info(f"[fallback] No se pudo leer credit_transactions overview: {e}")

        return overview

    # ---------- Créditos: link de compra ----------

    async def get_purchase_credits_link(
        self, user_id: int, redirect_path: str = "/dashboard/credits"
    ) -> PurchaseCreditsLinkDTO:
        """
        Devuelve el deep link del frontend para comprar créditos.
        """
        url = f"{self.frontend_base_url.rstrip('/')}/billing/credits?redirect={redirect_path}"
        return PurchaseCreditsLinkDTO(url=url)

    # ---------- Cerrar sesión ----------

    async def logout(self, user_id: int, session_id: Optional[str]) -> None:
        """
        Revoca la sesión actual del usuario.
        """
        try:
            await self.session_manager.revoke_session(user_id, session_id)
        except Exception as e:
            logger.error(f"No se pudo revocar la sesión: {e}")
            raise


# Alias para compatibilidad con otros módulos
UserProfileService = ProfileService

# Fin del archivo
