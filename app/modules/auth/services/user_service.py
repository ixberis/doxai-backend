# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/user_service.py

Servicio de usuarios y helpers de autenticación.

Refactor Fase 3:
- Se introduce el uso de UserRepository como capa de acceso a datos.
- Se mantiene el patrón de sesión flexible (session_factory o AsyncSession directa).
- Se preserva el helper get_current_user_from_token para retrocompatibilidad.

Autor: Ixchel Beristain
Actualizado: 2025-11-19
Actualizado: 2026-01-09
  - Evita ping/overhead cuando la sesión es prestada (reduce latencia en login).
  - get_by_id: NO consulta si user_id no es int (evita bigint=varchar).
  - get_current_user_from_token: resuelve por auth_user_id UUID (SSOT) primero.
  - Reduce ruido de logs (lecturas frecuentes a DEBUG).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Optional
from uuid import UUID as PyUUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.enums import UserStatus
from app.modules.auth.models.user_models import AppUser
from app.modules.auth.repositories import UserRepository
from app.modules.auth.security import oauth2_scheme, decode_access_token
from app.shared.database.database import get_async_session  # dependencia real

log = logging.getLogger(__name__)


class TokenDecodeError(Exception):
    """Excepción genérica si tu módulo de seguridad no expone una específica."""
    pass


def _is_callable(obj: Any) -> bool:
    try:
        return callable(obj)
    except Exception:
        return False


def _mask_email(email: str) -> str:
    e = (email or "").strip().lower()
    if not e or "@" not in e:
        return "unknown"
    local, domain = e.split("@", 1)
    return f"{local[:3]}***@{domain}" if len(local) >= 3 else f"{local[:1]}***@{domain}"


class UserService:
    """
    Servicio de usuarios (lectura/escritura) con DI flexible.
    Puede recibir:
      - session_factory: async_sessionmaker[AsyncSession] o callable que retorne AsyncSession
      - session: AsyncSession (sesión prestada)
    También tolera que accidentalmente te pasen una AsyncSession en 'session_factory'.

    Nota performance:
      - Si la sesión es PRESTADA (login/request-scope), NO hacemos ping preventivo.
        Eso evita roundtrips extra en endpoints hot (p.ej. /auth/login).
    """

    def __init__(
        self,
        session_factory: Optional[Any] = None,
        session: Optional[AsyncSession] = None,
    ) -> None:
        if session_factory is None and session is None:
            raise ValueError("UserService requiere session_factory o session")
        self._session_factory = session_factory
        self._session = session

    # ---------------------- Constructores para Depends ----------------------

    @classmethod
    def with_session_factory(cls, session_factory: Any) -> "UserService":
        """Crea un UserService a partir de una fábrica de sesiones."""
        return cls(session_factory=session_factory)

    @classmethod
    def with_session(cls, session: AsyncSession) -> "UserService":
        """Crea un UserService a partir de una AsyncSession ya creada."""
        return cls(session=session)

    # ---------------------- Gestión de sesión interna -----------------------

    def _using_borrowed_session(self) -> bool:
        """
        True si la sesión la aporta el caller (request-scope / prestada).
        En ese caso evitamos ping preventivo para no agregar latencia.
        """
        if self._session is not None:
            return True
        sf = self._session_factory
        return isinstance(sf, AsyncSession)

    @asynccontextmanager
    async def _session_scope(self):
        """
        Devuelve un AsyncSession usable:
          - Si hay 'session' explícita -> la usa (no la cierra).
          - Si 'session_factory' es AsyncSession -> la usa (no la cierra).
          - Si 'session_factory' es callable -> la invoca y cierra con 'async with'.
        """
        if self._session is not None:
            yield self._session
            return

        sf = self._session_factory
        if isinstance(sf, AsyncSession):
            yield sf
            return

        if _is_callable(sf):
            async with sf() as s:  # type: ignore[misc]
                yield s
            return

        raise RuntimeError(
            "UserService mal configurado: 'session_factory' no es AsyncSession ni callable."
        )

    async def _ping_db(self, session: AsyncSession, timeout_ms: int = 2000) -> None:
        """
        Verifica que la conexión esté viva y que no haya bloqueo general.
        Usa SET LOCAL statement_timeout y luego SELECT 1.
        """
        try:
            await session.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
        except Exception as e:
            # No es fatal si no es Postgres o no permite SET LOCAL
            log.debug("No se pudo aplicar statement_timeout local en ping: %s", e)

        try:
            await session.execute(text("SELECT 1"))
        except Exception as e:
            log.error("Ping DB FALLÓ: %s", e)
            raise

    async def _apply_stmt_timeout(self, session: AsyncSession, timeout_ms: int = 3000) -> None:
        """Aplica SET LOCAL statement_timeout para la consulta principal."""
        try:
            await session.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
            log.debug("statement_timeout local aplicado: %d ms", timeout_ms)
        except Exception as e:
            log.debug("No se pudo aplicar statement_timeout local a la consulta: %s", e)

    async def _pre_query_guards(
        self,
        session: AsyncSession,
        *,
        stmt_timeout_ms: int,
        ping_timeout_ms: int = 2000,
    ) -> None:
        """
        Guards previos a query:
          - Ping solo cuando NO usamos sesión prestada (para evitar overhead en login).
          - statement_timeout siempre best-effort.
        """
        if not self._using_borrowed_session():
            await self._ping_db(session, timeout_ms=ping_timeout_ms)
        await self._apply_stmt_timeout(session, timeout_ms=stmt_timeout_ms)

    # ----------------------------- Lecturas ---------------------------------

    async def get_by_email(self, email: str) -> Optional[AppUser]:
        """
        Obtiene un usuario por email (case-insensitive). Devuelve None si no existe.

        Performance:
          - En login normalmente se usa session prestada → NO hacemos ping preventivo.
          - statement_timeout se mantiene best-effort.
        """
        import time
        start = time.perf_counter()
        
        norm_email = (email or "").strip().lower()
        if not norm_email:
            return None

        async with self._session_scope() as session:
            await self._pre_query_guards(session, stmt_timeout_ms=3000)

            repo = UserRepository(session)
            query_start = time.perf_counter()
            try:
                user = await repo.get_by_email(norm_email)
                log.debug("Users.get_by_email ok (email=%s)", _mask_email(norm_email))
                return user
            except Exception as e:
                log.exception("Users.get_by_email ERROR email=%s error=%s", _mask_email(norm_email), e)
                raise

    async def exists_by_email(self, email: str) -> bool:
        """
        Indica si ya existe un usuario con ese email.
        Útil para validaciones de registro.
        """
        norm_email = (email or "").strip().lower()
        if not norm_email:
            return False

        async with self._session_scope() as session:
            await self._pre_query_guards(session, stmt_timeout_ms=3000)

            repo = UserRepository(session)
            try:
                exists = await repo.exists_by_email(norm_email)
                log.debug("Users.exists_by_email=%s (email=%s)", exists, _mask_email(norm_email))
                return exists
            except Exception as e:
                log.exception("Users.exists_by_email ERROR email=%s error=%s", _mask_email(norm_email), e)
                raise

    async def get_by_id(self, user_id: Any) -> Optional[AppUser]:
        """
        Recupera usuario por PK (INT).

        SSOT:
          - JWT sub SHOULD be auth_user_id (UUID), NO user_id (INT).
          - Por seguridad y para evitar bigint=varchar, si no es convertible a int, retornamos None.
        """
        # Normalizar user_id a entero cuando venga como string
        normalized_id: Any = user_id
        if isinstance(user_id, (str, bytes)):
            try:
                normalized_id = int(user_id)
            except ValueError:
                # NO consultamos con varchar contra bigint: eso rompe y puede abortar tx.
                log.warning("Users.get_by_id: user_id no convertible a int (skipping): %r", user_id)
                return None

        async with self._session_scope() as session:
            await self._pre_query_guards(session, stmt_timeout_ms=3000)

            repo = UserRepository(session)
            try:
                user = await repo.get_by_id(normalized_id)
                log.debug("Users.get_by_id ok (id=%s)", normalized_id)
                return user
            except Exception as e:
                log.exception("Users.get_by_id ERROR id=%s error=%s", normalized_id, e)
                raise

    async def get_by_auth_user_id(self, auth_user_id: Any) -> Optional[AppUser]:
        """
        Recupera usuario por auth_user_id (UUID SSOT).

        Este es el método preferido para resolver usuarios desde JWT sub.
        """
        # Normalizar a UUID si viene como string
        if isinstance(auth_user_id, str):
            try:
                auth_user_id = PyUUID(auth_user_id)
            except ValueError:
                log.warning("Users.get_by_auth_user_id: auth_user_id inválido: %r", auth_user_id)
                return None

        async with self._session_scope() as session:
            await self._pre_query_guards(session, stmt_timeout_ms=3000)

            repo = UserRepository(session)
            try:
                user = await repo.get_by_auth_user_id(auth_user_id)
                log.debug("Users.get_by_auth_user_id ok (auth_user_id=%s)", str(auth_user_id)[:8] + "...")
                return user
            except Exception as e:
                log.exception(
                    "Users.get_by_auth_user_id ERROR auth_user_id=%s error=%s",
                    str(auth_user_id)[:8] + "...",
                    e,
                )
                raise

    # ----------------------------- Escrituras -------------------------------

    async def add(self, user: AppUser) -> AppUser:
        """
        Inserta un nuevo usuario. Normaliza email a minúsculas.
        El commit y refresh se realizan en el repositorio.
        """
        if getattr(user, "user_email", None):
            user.user_email = user.user_email.strip().lower()

        async with self._session_scope() as session:
            # En creación sí vale la pena ping + timeout más amplio si la sesión no es prestada
            await self._pre_query_guards(session, stmt_timeout_ms=5000)

            repo = UserRepository(session)
            try:
                created = await repo.add(user)
                log.info("Users.add ← usuario creado (id=%s)", getattr(created, "user_id", None))
                return created
            except Exception as e:
                log.exception("Users.add ERROR: %s", e)
                raise

    async def save(self, user: AppUser) -> AppUser:
        """
        Actualiza un usuario existente. El commit y refresh se delegan al repositorio.
        """
        async with self._session_scope() as session:
            await self._pre_query_guards(session, stmt_timeout_ms=5000)

            repo = UserRepository(session)
            try:
                updated = await repo.save(user)
                log.info("Users.save ← usuario actualizado (id=%s)", getattr(updated, "user_id", None))
                return updated
            except Exception as e:
                log.exception("Users.save ERROR: %s", e)
                raise

    async def set_status(self, user: AppUser, status_value: UserStatus) -> AppUser:
        """
        Cambia el estatus lógico del usuario y persiste el cambio.
        """
        async with self._session_scope() as session:
            await self._pre_query_guards(session, stmt_timeout_ms=5000)

            repo = UserRepository(session)
            try:
                updated = await repo.set_status(user, status_value)
                log.info(
                    "Users.set_status ← usuario %s ahora en estado %s",
                    getattr(updated, "user_id", None),
                    status_value,
                )
                return updated
            except Exception as e:
                log.exception("Users.set_status ERROR: %s", e)
                raise

    # -------------------------- Helpers de estado ---------------------------

    async def is_active(self, user: AppUser) -> bool:
        """
        Verifica si el usuario está activo según UserStatus.
        """
        status_field = getattr(user, "user_status", None)
        if status_field is None:
            # Fallback: si no hay campo de estado, asumimos activo
            return True
        try:
            return status_field == UserStatus.active
        except Exception:
            return str(status_field) == getattr(UserStatus.active, "value", "active")


# ---------------------- Helper retro-compatible ----------------------


async def get_current_user_from_token(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_async_session),
) -> AppUser:
    """
    Decodifica el JWT, recupera el usuario y valida que esté activo.
    Mantiene compatibilidad con código legado que dependía de este helper.

    SSOT:
      - sub debería ser auth_user_id (UUID).
      - fallback legacy: sub puede ser user_id (INT) durante transición.
    """
    try:
        payload = decode_access_token(token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
        ) from e

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token sin 'sub'")

    repo = UserRepository(session)

    # 1) Intentar SSOT (UUID)
    user: Optional[AppUser] = None
    try:
        auth_user_id = PyUUID(str(sub))
        user = await repo.get_by_auth_user_id(auth_user_id)
    except Exception:
        user = None

    # 2) Fallback legacy (INT)
    if user is None:
        try:
            user_id_int = int(str(sub))
            user = await repo.get_by_id(user_id_int)
        except Exception:
            user = None

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado")

    # Checamos flag de actividad (si existe)
    if hasattr(user, "is_active") and not getattr(user, "is_active"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no autorizado")

    return user


__all__ = ["UserService", "get_current_user_from_token"]

# Fin del script backend/app/modules/auth/services/user_service.py





