
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/repositories/login_attempt_repository.py

Repositorio para auditoría de intentos de login (LoginAttempt).
Permite registrar intentos y consultar fallos recientes para
soportar rate limiting y métricas.

Autor: Ixchel Beristain
Fecha: 19/11/2025
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.enums import LoginFailureReason
from app.modules.auth.models.login_models import LoginAttempt


class LoginAttemptRepository:
    """Repositorio de LoginAttempt."""

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
    async def record_attempt(
        self,
        *,
        user_id: Optional[int] = None,
        success: bool,
        reason: Optional[LoginFailureReason] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> LoginAttempt:
        """
        Registra un intento de login.

        Args:
            user_id: Identificador del usuario.
            success: True si el login fue exitoso.
            reason: Razón de fallo (si success=False).
            ip_address: IP origen (opcional).
            user_agent: User-Agent del cliente (opcional).
            created_at: Momento del intento (opcional; por defecto ahora).
        """
        if created_at is None:
            created_at = datetime.now(timezone.utc)

        attempt = LoginAttempt(
            user_id=user_id,
            success=success,
            reason=reason,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=created_at,
        )
        self._db.add(attempt)
        await self._db.commit()
        await self._db.refresh(attempt)
        return attempt

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def list_recent_failures(
        self,
        *,
        user_id: int,
        since: datetime,
    ) -> Sequence[LoginAttempt]:
        """
        Lista intentos fallidos de un usuario desde un momento dado.
        """
        stmt = (
            select(LoginAttempt)
            .where(LoginAttempt.user_id == user_id)
            .where(LoginAttempt.success.is_(False))
            .where(LoginAttempt.created_at >= since)
            .order_by(LoginAttempt.created_at.desc())
        )
        result = await self._db.execute(stmt)
        return result.scalars().all()

    async def count_recent_failures(
        self,
        *,
        user_id: int,
        since: datetime,
    ) -> int:
        """
        Cuenta intentos fallidos recientes de un usuario.

        Útil para implementar lógica de bloqueo adicional basada
        en la tabla histórica (además del rate limiting in-memory).
        """
        stmt = (
            select(func.count())
            .select_from(LoginAttempt)
            .where(LoginAttempt.user_id == user_id)
            .where(LoginAttempt.success.is_(False))
            .where(LoginAttempt.created_at >= since)
        )
        result = await self._db.execute(stmt)
        return int(result.scalar_one() or 0)


__all__ = ["LoginAttemptRepository"]

# Fin del archivo backend/app/modules/auth/repositories/login_attempt_repository.py
