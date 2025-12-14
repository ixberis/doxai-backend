
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

from typing import Optional, Sequence

from sqlalchemy import func, select
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


__all__ = ["UserRepository"]

# Fin del archivo backend/app/modules/auth/repositories/user_repository.py
