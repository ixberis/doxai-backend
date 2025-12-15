
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/repositories/user_repository.py

Repositorio de acceso a datos para AppUser (usuarios de la plataforma DoxAI).
Encapsula operaciones CRUD básicas y consultas frecuentes sobre la tabla
app_users, dejando la lógica de negocio en los servicios superiores.

Autor: Ixchel Beristain
Fecha: 19/11/2025
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.enums import UserStatus
from app.modules.auth.models.user_models import AppUser


class UserRepository:
    """Repositorio de usuarios (AppUser)."""

    def __init__(self, db: AsyncSession) -> None:
        """
        Inicializa el repositorio con una sesión asíncrona.

        Args:
            db: AsyncSession activa contra la base de datos.
        """
        self._db = db

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(self, user_id: int) -> Optional[AppUser]:
        """
        Obtiene un usuario por su identificador interno (PK).
        Devuelve None si no existe.
        """
        stmt = select(AppUser).where(AppUser.user_id == user_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[AppUser]:
        """
        Obtiene un usuario por email (normalizado en minúsculas).
        Devuelve None si no existe.
        """
        norm_email = (email or "").strip().lower()
        if not norm_email:
            return None

        stmt = select(AppUser).where(
            func.lower(AppUser.user_email) == norm_email
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def exists_by_email(self, email: str) -> bool:
        """
        Indica si ya existe un usuario con el email dado.
        Útil para validaciones de registro.
        """
        norm_email = (email or "").strip().lower()
        if not norm_email:
            return False

        stmt = select(func.count()).select_from(AppUser).where(
            func.lower(AppUser.user_email) == norm_email
        )
        result = await self._db.execute(stmt)
        count = result.scalar_one() or 0
        return count > 0

    async def list_by_status(
        self,
        status: Optional[UserStatus] = None,
        limit: int | None = None,
    ) -> Sequence[AppUser]:
        """
        Lista usuarios, opcionalmente filtrando por estado.

        Args:
            status: Estado del usuario (UserStatus) o None para todos.
            limit: Máximo de filas a devolver, o None sin límite explícito.
        """
        stmt = select(AppUser)
        if status is not None:
            stmt = stmt.where(AppUser.user_status == status)
        stmt = stmt.order_by(AppUser.user_created_at.desc())
        if limit is not None and limit > 0:
            stmt = stmt.limit(limit)

        result = await self._db.execute(stmt)
        return result.scalars().all()

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def add(self, user: AppUser) -> AppUser:
        """
        Inserta un nuevo usuario y confirma la transacción.

        Nota:
            Se asume que las validaciones (email único, contraseña ya
            hasheada, etc.) se hicieron en el servicio.
        """
        self._db.add(user)
        await self._db.commit()
        await self._db.refresh(user)
        return user

    async def save(self, user: AppUser) -> AppUser:
        """
        Actualiza un usuario existente, confirmando la transacción.

        Usa merge() para manejar entidades potencialmente desprendidas.
        """
        managed = await self._db.merge(user)
        await self._db.commit()
        await self._db.refresh(managed)
        return managed

    async def set_status(
        self,
        user: AppUser,
        status: UserStatus,
    ) -> AppUser:
        """
        Cambia el estatus lógico del usuario y persiste el cambio.
        """
        user.user_status = status
        managed = await self._db.merge(user)
        await self._db.commit()
        await self._db.refresh(managed)
        return managed

    async def claim_welcome_email_if_pending(
        self,
        user_id: int,
        stale_ttl_minutes: int = 15,
    ) -> tuple[bool, int]:
        """
        Claim atómico para envío de welcome email (anti-race + anti-stuck).

        Ejecuta:
            UPDATE app_users
            SET welcome_email_status = 'pending',
                welcome_email_claimed_at = now(),
                welcome_email_attempts = welcome_email_attempts + 1,
                welcome_email_last_error = NULL  -- limpia error previo
            WHERE user_id = :user_id
              AND (
                welcome_email_status IS NULL
                OR (welcome_email_status = 'pending' 
                    AND welcome_email_claimed_at < now() - (:ttl_minutes * interval '1 minute'))
              )

        Retorna tupla (claimed: bool, attempts: int).
        - claimed=True si este proceso ganó la carrera
        - attempts es el nuevo contador después del claim

        Importante: NO hace commit; el servicio maneja la transacción.
        """
        from sqlalchemy import text
        
        # UPDATE con reclaim de pending stale (parámetros seguros, schema explícito)
        stmt = text("""
            UPDATE public.app_users
            SET welcome_email_status = 'pending',
                welcome_email_claimed_at = now(),
                welcome_email_attempts = welcome_email_attempts + 1,
                welcome_email_last_error = NULL
            WHERE user_id = :user_id
              AND (
                welcome_email_status IS NULL
                OR (
                    welcome_email_status = 'pending'
                    AND welcome_email_claimed_at < now() - (:ttl_minutes * interval '1 minute')
                )
              )
            RETURNING welcome_email_attempts
        """)
        
        result = await self._db.execute(
            stmt,
            {"user_id": user_id, "ttl_minutes": stale_ttl_minutes},
        )
        row = result.fetchone()
        
        if row:
            return (True, row[0])
        return (False, 0)

    async def mark_welcome_email_sent(self, user_id: int) -> None:
        """
        Marca el correo como enviado exitosamente.
        Llamar después de enviar el correo.
        """
        stmt = (
            update(AppUser)
            .where(AppUser.user_id == user_id)
            .values(
                welcome_email_status="sent",
                welcome_email_sent_at=datetime.now(timezone.utc),
                welcome_email_last_error=None,
            )
        )
        await self._db.execute(stmt)
        # NO commit aquí

    async def mark_welcome_email_failed(self, user_id: int, error: str) -> None:
        """
        Marca el correo como fallido con mensaje de error.
        Permite reintentos manuales posteriores.
        """
        stmt = (
            update(AppUser)
            .where(AppUser.user_id == user_id)
            .values(
                welcome_email_status="failed",
                welcome_email_last_error=error[:500] if error else "Unknown error",
            )
        )
        await self._db.execute(stmt)
        # NO commit aquí


__all__ = ["UserRepository"]

# Fin del archivo backend/app/modules/auth/repositories/user_repository.py
