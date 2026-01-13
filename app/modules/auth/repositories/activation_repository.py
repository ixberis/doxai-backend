# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/repositories/activation_repository.py

Repositorio para la gestión de registros de activación de cuenta
(AccountActivation). Encapsula las consultas más comunes sobre tokens
de activación y activaciones pendientes.

Autor: Ixchel Beristain
Fecha: 19/11/2025
"""

from __future__ import annotations

import logging
import warnings
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.enums import ActivationStatus
from app.modules.auth.models.activation_models import AccountActivation


class ActivationRepository:
    """Repositorio de AccountActivation."""

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
    async def create_activation(
        self,
        *,
        user_id: int,
        auth_user_id: UUID,
        token: str,
        expires_at: datetime,
        status: ActivationStatus = ActivationStatus.sent,
    ) -> AccountActivation:
        """
        Crea un nuevo registro de activación para un usuario.

        Args:
            user_id: Identificador interno del usuario (FK a app_users.user_id).
            auth_user_id: UUID SSOT del usuario (FK a app_users.auth_user_id).
            token: Token de activación único.
            expires_at: Fecha/hora de expiración.
            status: Estado inicial (por defecto ActivationStatus.sent).

        Returns:
            Instancia persistida de AccountActivation.
        """
        activation = AccountActivation(
            user_id=user_id,
            auth_user_id=auth_user_id,  # UUID nativo (DB 2.0 SSOT)
            token=token,
            status=status,
            expires_at=expires_at,
        )
        self._db.add(activation)
        await self._db.commit()
        await self._db.refresh(activation)
        return activation

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(self, activation_id: int) -> Optional[AccountActivation]:
        """
        Obtiene un registro de activación por ID.
        
        Útil para re-fetch después de rollback (SQLAlchemy async safety).
        """
        stmt = select(AccountActivation).where(AccountActivation.id == activation_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_token(self, token: str) -> Optional[AccountActivation]:
        """
        Obtiene un registro de activación por token.

        No filtra por expiración ni estado; la lógica de negocio decide
        qué hacer con registros expirados o ya consumidos.
        """
        stmt = select(AccountActivation).where(AccountActivation.token == token)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_pending_for_user(
        self,
        user_id: int,
        now: Optional[datetime] = None,
    ) -> Optional[AccountActivation]:
        """
        Obtiene la activación pendiente más reciente para un usuario.

        Criterios:
            - status = ActivationStatus.sent
            - consumed_at IS NULL
            - expires_at > now (si se proporciona)
        """
        if now is None:
            now = datetime.now(timezone.utc)

        stmt = (
            select(AccountActivation)
            .where(AccountActivation.user_id == user_id)
            .where(AccountActivation.status == ActivationStatus.sent)
            .where(AccountActivation.consumed_at.is_(None))
            .where(AccountActivation.expires_at > now)
            .order_by(AccountActivation.created_at.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def count_pending_for_user(self, user_id: int) -> int:
        """
        Cuenta cuántos registros de activación pendientes tiene un usuario.
        """
        stmt = (
            select(func.count())
            .select_from(AccountActivation)
            .where(AccountActivation.user_id == user_id)
            .where(AccountActivation.status == ActivationStatus.sent)
            .where(AccountActivation.consumed_at.is_(None))
        )
        result = await self._db.execute(stmt)
        return int(result.scalar_one() or 0)

    # ------------------------------------------------------------------
    # Actualizaciones
    # ------------------------------------------------------------------
    async def mark_as_consumed(
        self,
        activation: AccountActivation,
        *,
        consumed_at: Optional[datetime] = None,
    ) -> AccountActivation:
        """
        Marca un registro de activación como consumido.

        Args:
            activation: Instancia existente de AccountActivation.
            consumed_at: Momento de consumo; por defecto now UTC.
        """
        if consumed_at is None:
            consumed_at = datetime.now(timezone.utc)

        activation.status = ActivationStatus.consumed
        activation.consumed_at = consumed_at

        managed = await self._db.merge(activation)
        await self._db.commit()
        await self._db.refresh(managed)
        return managed

    # ------------------------------------------------------------------
    # Deprecated (wrapper para compatibilidad interna)
    # ------------------------------------------------------------------
    async def mark_as_used(
        self,
        activation: AccountActivation,
        *,
        used_at: Optional[datetime] = None,
    ) -> AccountActivation:
        """
        DEPRECATED: Usar mark_as_consumed() en su lugar.
        
        Este wrapper existe para compatibilidad temporal con código
        legacy que aún use 'mark_as_used'. Emite un DeprecationWarning.
        """
        logger = logging.getLogger(__name__)
        logger.warning(
            "mark_as_used is deprecated; use mark_as_consumed instead",
            extra={"activation_id": getattr(activation, "id", None)},
        )
        warnings.warn(
            "mark_as_used is deprecated, use mark_as_consumed",
            DeprecationWarning,
            stacklevel=2,
        )
        return await self.mark_as_consumed(activation, consumed_at=used_at)


__all__ = ["ActivationRepository"]

# Fin del archivo backend/app/modules/auth/repositories/activation_repository.py

