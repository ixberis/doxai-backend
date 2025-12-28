# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/session_service.py

Servicio para gestión de sesiones de usuario.
Registra, revoca y consulta sesiones activas en la tabla user_sessions.

Responsabilidades:
- Crear sesión al login exitoso
- Revocar sesión al logout
- Contar sesiones activas para métricas

Autor: Ixchel Beristain
Fecha: 2025-12-28
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.shared.config.config_loader import get_settings

logger = logging.getLogger(__name__)


class SessionService:
    """
    Gestiona sesiones de usuario en public.user_sessions.
    
    Operaciones:
    - create_session: registra nueva sesión al login
    - revoke_session_by_token_hash: revoca por hash de token
    - revoke_all_sessions_for_user: revoca todas las sesiones de un usuario
    - count_active_sessions: cuenta sesiones activas (para métricas)
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()
        # TTL del access token en minutos (default 60)
        self._access_ttl_minutes = int(
            getattr(self.settings, "AUTH_ACCESS_TOKEN_TTL_MINUTES", 60)
        )

    @staticmethod
    def hash_token(token: str) -> str:
        """
        Genera hash SHA-256 del token para almacenar en DB.
        NUNCA almacenar tokens en claro.
        """
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def create_session(
        self,
        user_id: int,
        access_token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        ttl_minutes: Optional[int] = None,
    ) -> bool:
        """
        Registra una nueva sesión en user_sessions.
        
        Args:
            user_id: ID del usuario
            access_token: Token de acceso (se almacena hasheado)
            ip_address: IP del cliente
            user_agent: User-Agent del cliente
            ttl_minutes: TTL de la sesión en minutos (default: AUTH_ACCESS_TOKEN_TTL_MINUTES)
        
        Returns:
            True si se creó correctamente, False en caso de error.
        """
        ttl = ttl_minutes or self._access_ttl_minutes
        token_hash = self.hash_token(access_token)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=ttl)
        
        try:
            # Usar query directa para compatibilidad con cualquier estado del ORM
            q = text("""
                INSERT INTO public.user_sessions 
                    (user_id, token_type, token_hash, issued_at, expires_at, ip_address, user_agent)
                VALUES 
                    (:user_id, 'access', :token_hash, :issued_at, :expires_at, :ip_address, :user_agent)
                ON CONFLICT (token_hash) DO UPDATE SET
                    issued_at = EXCLUDED.issued_at,
                    expires_at = EXCLUDED.expires_at,
                    revoked_at = NULL
            """)
            await self.db.execute(q, {
                "user_id": user_id,
                "token_hash": token_hash,
                "issued_at": now,
                "expires_at": expires_at,
                "ip_address": ip_address,
                "user_agent": user_agent,
            })
            await self.db.commit()
            
            logger.info(
                "session_created user_id=%s expires_at=%s ip=%s",
                user_id,
                expires_at.isoformat(),
                ip_address or "unknown",
            )
            return True
            
        except Exception as e:
            logger.warning("create_session failed: %s", e)
            await self.db.rollback()
            return False

    async def revoke_session_by_token_hash(self, token_hash: str) -> bool:
        """
        Revoca una sesión específica por su token_hash.
        
        Returns:
            True si se revocó, False si no existía o hubo error.
        """
        now = datetime.now(timezone.utc)
        try:
            q = text("""
                UPDATE public.user_sessions 
                SET revoked_at = :now
                WHERE token_hash = :token_hash 
                  AND revoked_at IS NULL
            """)
            result = await self.db.execute(q, {"token_hash": token_hash, "now": now})
            await self.db.commit()
            
            rows_affected = result.rowcount
            if rows_affected > 0:
                logger.info("session_revoked token_hash=%s...", token_hash[:16])
                return True
            return False
            
        except Exception as e:
            logger.warning("revoke_session_by_token_hash failed: %s", e)
            await self.db.rollback()
            return False

    async def revoke_session_by_token(self, access_token: str) -> bool:
        """
        Revoca una sesión por el token de acceso original.
        """
        token_hash = self.hash_token(access_token)
        return await self.revoke_session_by_token_hash(token_hash)

    async def revoke_all_sessions_for_user(self, user_id: int) -> int:
        """
        Revoca todas las sesiones activas de un usuario.
        
        Returns:
            Número de sesiones revocadas.
        """
        now = datetime.now(timezone.utc)
        try:
            q = text("""
                UPDATE public.user_sessions 
                SET revoked_at = :now
                WHERE user_id = :user_id 
                  AND revoked_at IS NULL
                  AND expires_at > :now
            """)
            result = await self.db.execute(q, {"user_id": user_id, "now": now})
            await self.db.commit()
            
            rows_affected = result.rowcount
            logger.info("sessions_revoked_all user_id=%s count=%d", user_id, rows_affected)
            return rows_affected
            
        except Exception as e:
            logger.warning("revoke_all_sessions_for_user failed: %s", e)
            await self.db.rollback()
            return 0

    async def count_active_sessions(self) -> int:
        """
        Cuenta sesiones activas (no revocadas, no expiradas).
        Para métricas de Auth Metrics.
        """
        try:
            q = text("""
                SELECT COUNT(*) 
                FROM public.user_sessions 
                WHERE revoked_at IS NULL 
                  AND expires_at > NOW()
            """)
            result = await self.db.execute(q)
            row = result.first()
            return int(row[0]) if row and row[0] else 0
        except Exception as e:
            logger.warning("count_active_sessions failed: %s", e)
            return 0


__all__ = ["SessionService"]

# Fin del archivo backend/app/modules/auth/services/session_service.py
