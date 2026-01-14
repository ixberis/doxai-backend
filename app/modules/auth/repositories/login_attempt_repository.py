# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/repositories/login_attempt_repository.py

Repositorio para auditoría de intentos de login (LoginAttempt).
Permite registrar intentos y consultar fallos recientes para
soportar rate limiting y métricas.

BD 2.0 P0: Registra TODOS los intentos incluyendo user_not_found.

Autor: Ixchel Beristain
Fecha: 19/11/2025
Updated: 2026-01-14 - Soporte para user_not_found (nullable auth_user_id/user_id)
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.enums import LoginFailureReason
from app.modules.auth.models.login_models import LoginAttempt


def _compute_email_hash(email: str) -> str:
    """
    Computa SHA-256 del email normalizado para trazabilidad sin PII.
    
    El hash permite:
    - Agrupar intentos por email sin exponer el email real
    - Rate limiting analysis
    - Detección de ataques de fuerza bruta
    """
    normalized = email.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


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
        auth_user_id: Optional[UUID] = None,
        success: bool,
        reason: Optional[LoginFailureReason] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        email: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> LoginAttempt:
        """
        Registra un intento de login.

        BD 2.0 P0: Registra TODOS los intentos incluyendo user_not_found.
        
        Args:
            user_id: Identificador interno del usuario (NULL si user_not_found).
            auth_user_id: UUID SSOT del usuario (NULL si user_not_found).
            success: True si el login fue exitoso.
            reason: Razón de fallo (si success=False).
            ip_address: IP origen (opcional).
            user_agent: User-Agent del cliente (opcional).
            email: Email del intento (se hashea, no se guarda raw).
            created_at: Momento del intento (opcional; por defecto ahora).
        """
        if created_at is None:
            created_at = datetime.now(timezone.utc)

        # Compute email_hash para trazabilidad sin PII
        email_hash = _compute_email_hash(email) if email else None

        attempt = LoginAttempt(
            user_id=user_id,
            auth_user_id=auth_user_id,
            success=success,
            reason=reason,
            ip_address=ip_address,
            user_agent=user_agent,
            email_hash=email_hash,
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

