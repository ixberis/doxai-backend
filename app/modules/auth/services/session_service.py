# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/session_service.py

Servicio para gestión de sesiones de usuario.
Registra, revoca y consulta sesiones activas en la tabla user_sessions.

Responsabilidades:
- Crear sesión al login exitoso
- Revocar sesión al logout
- Contar sesiones activas para métricas
- Política single-session: al crear sesión, revocar todas las previas

Autor: Ixchel Beristain
Fecha: 2025-12-28
Updated: 2025-01-14 - Single-session policy con advisory lock
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.shared.config.config_loader import get_settings

logger = logging.getLogger(__name__)


# Feature flag for single-session policy
# Default: enabled (1 sesión activa por usuario)
SINGLE_SESSION_ENABLED = os.getenv(
    "SINGLE_SESSION_ENABLED", "1"
).lower() in ("1", "true", "yes")


class SessionService:
    """
    Gestiona sesiones de usuario en public.user_sessions.
    
    Operaciones:
    - create_session: registra nueva sesión al login (legacy, multi-session)
    - create_single_session: registra sesión única, revocando previas (single-session)
    - revoke_session_by_token_hash: revoca por hash de token
    - revoke_all_sessions_for_user: revoca todas las sesiones de un usuario
    - count_active_sessions: cuenta sesiones activas (para métricas)
    
    Single-Session Policy:
    - Cuando SINGLE_SESSION_ENABLED=1, create_session() usa create_single_session()
    - Advisory lock por auth_user_id previene race conditions
    - Garantiza: máximo 1 sesión activa por usuario en todo momento
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

    async def _acquire_user_advisory_lock(self, auth_user_id: UUID) -> bool:
        """
        Adquiere advisory lock transaccional por auth_user_id.
        El lock se libera automáticamente al commit/rollback.
        
        IMPORTANTE: Usar CAST(:param AS text) en lugar de :param::text
        porque SQLAlchemy text() con bind params no soporta :: cast syntax.
        
        Returns:
            True si se adquirió el lock, False si falló.
        """
        try:
            # CAST(...AS text) es la forma correcta para binds con SQLAlchemy text()
            # hashtext() genera un entero estable basado en el UUID string
            q = text("SELECT pg_advisory_xact_lock(hashtext(CAST(:auth_user_id AS text)))")
            await self.db.execute(q, {"auth_user_id": str(auth_user_id)})
            return True
        except Exception as e:
            logger.warning("advisory_lock_failed: auth_user_id=%s error=%s", 
                          str(auth_user_id)[:8] + "...", e)
            return False

    async def _revoke_active_sessions_for_auth_user(
        self,
        auth_user_id: UUID,
        *,
        exclude_token_hash: Optional[str] = None,
    ) -> int:
        """
        Revoca todas las sesiones activas de un auth_user_id.
        
        Args:
            auth_user_id: UUID del usuario (BD 2.0 SSOT)
            exclude_token_hash: Si se proporciona, NO revoca esta sesión
        
        Returns:
            Número de sesiones revocadas.
        """
        now = datetime.now(timezone.utc)
        
        if exclude_token_hash:
            q = text("""
                UPDATE public.user_sessions 
                SET revoked_at = :now
                WHERE auth_user_id = :auth_user_id 
                  AND revoked_at IS NULL
                  AND expires_at > :now
                  AND token_hash != :exclude_token_hash
            """)
            params = {
                "auth_user_id": auth_user_id,
                "now": now,
                "exclude_token_hash": exclude_token_hash,
            }
        else:
            q = text("""
                UPDATE public.user_sessions 
                SET revoked_at = :now
                WHERE auth_user_id = :auth_user_id 
                  AND revoked_at IS NULL
                  AND expires_at > :now
            """)
            params = {"auth_user_id": auth_user_id, "now": now}
        
        result = await self.db.execute(q, params)
        return result.rowcount or 0

    async def create_single_session(
        self,
        *,
        user_id: int,
        auth_user_id: UUID,
        access_token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        ttl_minutes: Optional[int] = None,
    ) -> Tuple[bool, int]:
        """
        Crea sesión única para el usuario, revocando todas las previas.
        
        Usa advisory lock transaccional para garantizar atomicidad y
        prevenir race conditions en logins concurrentes.
        
        Args:
            user_id: ID interno del usuario
            auth_user_id: UUID SSOT del usuario (BD 2.0) - REQUERIDO
            access_token: Token de acceso (se almacena hasheado)
            ip_address: IP del cliente
            user_agent: User-Agent del cliente
            ttl_minutes: TTL de la sesión en minutos
        
        Returns:
            Tuple[bool, int]: (éxito, número de sesiones previas revocadas)
        """
        ttl = ttl_minutes or self._access_ttl_minutes
        token_hash = self.hash_token(access_token)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=ttl)
        revoked_count = 0
        
        try:
            # 1. Adquirir advisory lock transaccional
            lock_acquired = await self._acquire_user_advisory_lock(auth_user_id)
            if not lock_acquired:
                logger.warning(
                    "single_session_lock_failed: auth_user_id=%s",
                    str(auth_user_id)[:8] + "...",
                )
                # Fallback: proceder sin lock (best-effort)
            
            # 2. Revocar sesiones activas previas del mismo usuario
            revoked_count = await self._revoke_active_sessions_for_auth_user(
                auth_user_id
            )
            
            # 3. Insertar nueva sesión
            q = text("""
                INSERT INTO public.user_sessions 
                    (user_id, auth_user_id, token_type, token_hash, issued_at, expires_at, ip_address, user_agent)
                VALUES 
                    (:user_id, :auth_user_id, 'access', :token_hash, :issued_at, :expires_at, :ip_address, :user_agent)
                ON CONFLICT (token_hash) DO UPDATE SET
                    issued_at = EXCLUDED.issued_at,
                    expires_at = EXCLUDED.expires_at,
                    revoked_at = NULL
            """)
            await self.db.execute(q, {
                "user_id": user_id,
                "auth_user_id": auth_user_id,
                "token_hash": token_hash,
                "issued_at": now,
                "expires_at": expires_at,
                "ip_address": ip_address,
                "user_agent": user_agent,
            })
            
            # 4. Commit (libera advisory lock)
            await self.db.commit()
            
            # Log estructurado
            if revoked_count > 0:
                logger.info(
                    "single_session_revoke_previous auth_user_id=%s revoked_count=%d ip=%s",
                    str(auth_user_id)[:8] + "...",
                    revoked_count,
                    ip_address or "unknown",
                )
            
            logger.info(
                "session_created_single_session user_id=%s auth_user_id=%s expires_at=%s ip=%s",
                user_id,
                str(auth_user_id)[:8] + "...",
                expires_at.isoformat(),
                ip_address or "unknown",
            )
            return True, revoked_count
            
        except Exception as e:
            logger.exception(
                "create_single_session failed: user_id=%s auth_user_id=%s error=%s",
                user_id,
                str(auth_user_id)[:8] + "...",
                e,
            )
            await self.db.rollback()
            return False, 0

    async def create_session(
        self,
        *,
        user_id: int,
        auth_user_id: UUID,
        access_token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        ttl_minutes: Optional[int] = None,
    ) -> bool:
        """
        Registra una nueva sesión en user_sessions.
        
        SINGLE-SESSION POLICY:
        - Si SINGLE_SESSION_ENABLED=1 (default), usa create_single_session()
          que revoca todas las sesiones previas antes de crear la nueva.
        - Si SINGLE_SESSION_ENABLED=0, crea sesión sin revocar previas (legacy).
        
        BD 2.0: Requiere auth_user_id (UUID SSOT) - NOT NULL en DB.
        
        Args:
            user_id: ID interno del usuario
            auth_user_id: UUID SSOT del usuario (BD 2.0) - REQUERIDO
            access_token: Token de acceso (se almacena hasheado)
            ip_address: IP del cliente
            user_agent: User-Agent del cliente
            ttl_minutes: TTL de la sesión en minutos (default: AUTH_ACCESS_TOKEN_TTL_MINUTES)
        
        Returns:
            True si se creó correctamente, False en caso de error.
        """
        # Route to single-session if enabled
        if SINGLE_SESSION_ENABLED:
            success, _ = await self.create_single_session(
                user_id=user_id,
                auth_user_id=auth_user_id,
                access_token=access_token,
                ip_address=ip_address,
                user_agent=user_agent,
                ttl_minutes=ttl_minutes,
            )
            return success
        
        # Legacy multi-session path
        ttl = ttl_minutes or self._access_ttl_minutes
        token_hash = self.hash_token(access_token)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=ttl)
        
        try:
            q = text("""
                INSERT INTO public.user_sessions 
                    (user_id, auth_user_id, token_type, token_hash, issued_at, expires_at, ip_address, user_agent)
                VALUES 
                    (:user_id, :auth_user_id, 'access', :token_hash, :issued_at, :expires_at, :ip_address, :user_agent)
                ON CONFLICT (token_hash) DO UPDATE SET
                    issued_at = EXCLUDED.issued_at,
                    expires_at = EXCLUDED.expires_at,
                    revoked_at = NULL
            """)
            await self.db.execute(q, {
                "user_id": user_id,
                "auth_user_id": auth_user_id,
                "token_hash": token_hash,
                "issued_at": now,
                "expires_at": expires_at,
                "ip_address": ip_address,
                "user_agent": user_agent,
            })
            await self.db.commit()
            
            logger.info(
                "session_created user_id=%s auth_user_id=%s expires_at=%s ip=%s",
                user_id,
                str(auth_user_id)[:8] + "...",
                expires_at.isoformat(),
                ip_address or "unknown",
            )
            return True
            
        except Exception as e:
            logger.exception("create_session failed: user_id=%s error=%s", user_id, e)
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
        Revoca todas las sesiones activas de un usuario (por user_id legacy).
        
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

    async def revoke_all_sessions_for_auth_user(self, auth_user_id: UUID) -> int:
        """
        Revoca todas las sesiones activas de un usuario por auth_user_id (BD 2.0 SSOT).
        
        Returns:
            Número de sesiones revocadas.
        """
        try:
            revoked = await self._revoke_active_sessions_for_auth_user(auth_user_id)
            await self.db.commit()
            logger.info(
                "sessions_revoked_all_by_auth_user auth_user_id=%s count=%d",
                str(auth_user_id)[:8] + "...",
                revoked,
            )
            return revoked
        except Exception as e:
            logger.warning("revoke_all_sessions_for_auth_user failed: %s", e)
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

    async def count_active_sessions_for_auth_user(self, auth_user_id: UUID) -> int:
        """
        Cuenta sesiones activas de un usuario específico.
        Usado para verificar política single-session.
        """
        try:
            q = text("""
                SELECT COUNT(*) 
                FROM public.user_sessions 
                WHERE auth_user_id = :auth_user_id
                  AND revoked_at IS NULL 
                  AND expires_at > NOW()
            """)
            result = await self.db.execute(q, {"auth_user_id": auth_user_id})
            row = result.first()
            return int(row[0]) if row and row[0] else 0
        except Exception as e:
            logger.warning("count_active_sessions_for_auth_user failed: %s", e)
            return 0


__all__ = ["SessionService", "SINGLE_SESSION_ENABLED"]

# Fin del archivo backend/app/modules/auth/services/session_service.py
