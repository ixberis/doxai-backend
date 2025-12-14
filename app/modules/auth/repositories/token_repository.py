
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/repositories/token_repository.py

Repositorio para la gestión de sesiones de usuario y tokens persistidos
(UserSession). Permite crear, revocar y consultar sesiones activas para
soportar funcionalidades como logout global o revocación selectiva.

Autor: Ixchel Beristain
Fecha: 19/11/2025
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.enums import TokenType
from app.modules.auth.models.login_models import UserSession


class TokenRepository:
    """Repositorio de sesiones de usuario (UserSession)."""

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
    async def create_session(
        self,
        *,
        user_id: int,
        token_type: TokenType,
        token_hash: str,
        expires_at: datetime,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        issued_at: Optional[datetime] = None,
    ) -> UserSession:
        """
        Crea una sesión de usuario persistida.

        Args:
            user_id: Identificador del usuario.
            token_type: Tipo de token (access, refresh, etc.).
            token_hash: Hash del token (no el token en claro).
            expires_at: Momento de expiración del token.
            ip_address: IP origen (opcional).
            user_agent: User-Agent del cliente (opcional).
            issued_at: Momento de emisión (opcional; por defecto now UTC).
        """
        if issued_at is None:
            issued_at = datetime.now(timezone.utc)

        session = UserSession(
            user_id=user_id,
            token_type=token_type,
            token_hash=token_hash,
            issued_at=issued_at,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self._db.add(session)
        await self._db.commit()
        await self._db.refresh(session)
        return session

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_token_hash(
        self,
        token_hash: str,
        *,
        only_active: bool = True,
        now: Optional[datetime] = None,
    ) -> Optional[UserSession]:
        """
        Obtiene una sesión por su hash de token.

        Args:
            token_hash: Hash del token.
            only_active: Si True, filtra por no revocada y no expirada.
            now: Momento de referencia para expiración; por defecto now UTC.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        stmt = select(UserSession).where(UserSession.token_hash == token_hash)
        if only_active:
            stmt = stmt.where(UserSession.revoked_at.is_(None))
            stmt = stmt.where(UserSession.expires_at > now)

        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active_sessions_for_user(
        self,
        user_id: int,
        *,
        now: Optional[datetime] = None,
    ) -> Sequence[UserSession]:
        """
        Lista sesiones activas de un usuario (no revocadas y no expiradas).
        """
        if now is None:
            now = datetime.now(timezone.utc)

        stmt = (
            select(UserSession)
            .where(UserSession.user_id == user_id)
            .where(UserSession.revoked_at.is_(None))
            .where(UserSession.expires_at > now)
            .order_by(UserSession.expires_at.desc())
        )
        result = await self._db.execute(stmt)
        return result.scalars().all()

    # ------------------------------------------------------------------
    # Actualizaciones
    # ------------------------------------------------------------------
    async def revoke_session(self, session: UserSession) -> UserSession:
        """
        Revoca una sesión individual (logout de un dispositivo).
        """
        if session.revoked_at is None:
            session.revoked_at = datetime.now(timezone.utc)

        managed = await self._db.merge(session)
        await self._db.commit()
        await self._db.refresh(managed)
        return managed

    async def revoke_all_sessions_for_user(self, user_id: int) -> int:
        """
        Revoca todas las sesiones activas de un usuario.

        Returns:
            Número de filas afectadas.
        """
        now = datetime.now(timezone.utc)
        stmt = (
            update(UserSession)
            .where(UserSession.user_id == user_id)
            .where(UserSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        result = await self._db.execute(stmt)
        await self._db.commit()
        # result.rowcount puede ser None con algunos backends; normalizamos a int
        return int(getattr(result, "rowcount", 0) or 0)

    async def count_active_sessions_for_user(
        self,
        user_id: int,
        *,
        now: Optional[datetime] = None,
    ) -> int:
        """
        Cuenta sesiones activas de un usuario.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        stmt = (
            select(func.count())
            .select_from(UserSession)
            .where(UserSession.user_id == user_id)
            .where(UserSession.revoked_at.is_(None))
            .where(UserSession.expires_at > now)
        )
        result = await self._db.execute(stmt)
        return int(result.scalar_one() or 0)


__all__ = ["TokenRepository"]

# Fin del archivo backend/app/modules/auth/repositories/token_repository.py
