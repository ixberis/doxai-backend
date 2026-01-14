
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/repositories/password_reset_repository.py

Repositorio para la tabla password_resets (PasswordReset).
Aunque en la versión actual el flujo de restablecimiento de contraseña
es stateless (solo JWT), este repositorio permite persistir tokens de
reset cuando se requiera un enfoque stateful o para auditoría.

BD 2.0 SSOT: auth_user_id es obligatorio para ownership/RLS.

Autor: Ixchel Beristain
Fecha: 19/11/2025
Updated: 2026-01-14 - auth_user_id obligatorio
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models.password_reset_models import PasswordReset


class PasswordResetRepository:
    """Repositorio de PasswordReset."""

    def __init__(self, db: AsyncSession) -> None:
        """
        Inicializa el repositorio con una sesión asíncrona.

        Args:
            db: AsyncSession activa contra la base de datos.
        """
        self._db = db

    # ------------------------------------------------------------------
    # Creación
    # ------------------------------------------------------------------
    async def create_reset(
        self,
        *,
        user_id: int,
        auth_user_id: UUID,
        token: str,
        expires_at: datetime,
    ) -> PasswordReset:
        """
        Crea un registro de restablecimiento de contraseña.

        Args:
            user_id: Identificador legacy del usuario.
            auth_user_id: UUID SSOT del usuario (BD 2.0).
            token: Token único de reset.
            expires_at: Momento de expiración del token.
        """
        reset = PasswordReset(
            user_id=user_id,
            auth_user_id=auth_user_id,
            token=token,
            expires_at=expires_at,
        )
        self._db.add(reset)
        await self._db.commit()
        await self._db.refresh(reset)
        return reset

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_token(
        self,
        token: str,
        *,
        only_valid: bool = True,
        now: Optional[datetime] = None,
    ) -> Optional[PasswordReset]:
        """
        Obtiene un registro de reset por token.

        Args:
            token: Token de reset.
            only_valid: Si True, filtra por no usado y no expirado.
            now: Momento de referencia para expiración; por defecto now UTC.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        stmt = select(PasswordReset).where(PasswordReset.token == token)
        if only_valid:
            stmt = stmt.where(PasswordReset.used_at.is_(None))
            stmt = stmt.where(PasswordReset.expires_at > now)

        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Actualizaciones
    # ------------------------------------------------------------------
    async def mark_as_used(
        self,
        reset: PasswordReset,
        *,
        used_at: Optional[datetime] = None,
    ) -> PasswordReset:
        """
        Marca un token de reset como usado.

        Args:
            reset: Instancia existente de PasswordReset.
            used_at: Momento de uso; por defecto now UTC.
        """
        if used_at is None:
            used_at = datetime.now(timezone.utc)

        reset.used_at = used_at
        managed = await self._db.merge(reset)
        await self._db.commit()
        await self._db.refresh(managed)
        return managed


__all__ = ["PasswordResetRepository"]

# Fin del archivo backend/app/modules/auth/repositories/password_reset_repository.py
