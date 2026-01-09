
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
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Optional

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


class UserService:
    """
    Servicio de usuarios (lectura/escritura) con DI flexible.
    Puede recibir:
      - session_factory: async_sessionmaker[AsyncSession] o callable que retorne AsyncSession
      - session: AsyncSession (sesión prestada)
    También tolera que accidentalmente te pasen una AsyncSession en 'session_factory'.
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

    # ----------------------------- Lecturas ---------------------------------

    async def get_by_email(self, email: str) -> Optional[AppUser]:
        """
        Obtiene un usuario por email (case-insensitive). Devuelve None si no existe.
        Añade ping y timeouts para evitar cuelgues en pasos críticos (p.ej. registro).
        """
        norm_email = (email or "").strip().lower()
        if not norm_email:
            return None

        async with self._session_scope() as session:
            await self._ping_db(session, timeout_ms=2000)
            await self._apply_stmt_timeout(session, timeout_ms=3000)

            repo = UserRepository(session)
            try:
                user = await repo.get_by_email(norm_email)
                log.info("Users.get_by_email ← consulta completada (email=%s)", norm_email)
                return user
            except Exception as e:
                log.error("Users.get_by_email ERROR: %s", e)
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
            await self._ping_db(session, timeout_ms=2000)
            await self._apply_stmt_timeout(session, timeout_ms=3000)

            repo = UserRepository(session)
            try:
                exists = await repo.exists_by_email(norm_email)
                log.info("Users.exists_by_email ← %s (email=%s)", exists, norm_email)
                return exists
            except Exception as e:
                log.error("Users.exists_by_email ERROR: %s", e)
                raise

    async def get_by_id(self, user_id: Any) -> Optional[AppUser]:
        """
        Recupera usuario por PK (INT).

        Nota:
            El modelo actual usa BIGINT, pero algunos flujos (JWT, activación, etc.)
            pasan el user_id como string. Aquí lo normalizamos a int siempre que
            sea posible, para evitar errores de tipo (bigint = varchar).
        """
        # Normalizar user_id a entero cuando venga como string
        normalized_id: Any = user_id
        if isinstance(user_id, (str, bytes)):
            try:
                normalized_id = int(user_id)
            except ValueError:
                # Si no se puede convertir, dejamos el valor original y dejamos que la consulta falle
                log.error("Users.get_by_id: user_id inválido no convertible a int: %r", user_id)

        async with self._session_scope() as session:
            await self._ping_db(session, timeout_ms=2000)
            await self._apply_stmt_timeout(session, timeout_ms=3000)

            repo = UserRepository(session)
            try:
                user = await repo.get_by_id(normalized_id)
                log.info("Users.get_by_id ← completado (id=%s)", normalized_id)
                return user
            except Exception as e:
                log.error("Users.get_by_id ERROR: %s", e)
                raise

    async def get_by_auth_user_id(self, auth_user_id) -> Optional[AppUser]:
        """
        Recupera usuario por auth_user_id (UUID SSOT).
        
        Este es el método preferido para resolver usuarios desde JWT sub.
        """
        from uuid import UUID as PyUUID
        
        # Normalizar a UUID si viene como string
        if isinstance(auth_user_id, str):
            try:
                auth_user_id = PyUUID(auth_user_id)
            except ValueError:
                log.error("Users.get_by_auth_user_id: auth_user_id inválido: %r", auth_user_id)
                return None

        async with self._session_scope() as session:
            await self._ping_db(session, timeout_ms=2000)
            await self._apply_stmt_timeout(session, timeout_ms=3000)

            repo = UserRepository(session)
            try:
                user = await repo.get_by_auth_user_id(auth_user_id)
                log.info("Users.get_by_auth_user_id ← completado (auth_user_id=%s)", auth_user_id)
                return user
            except Exception as e:
                log.error("Users.get_by_auth_user_id ERROR: %s", e)
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
            await self._ping_db(session, timeout_ms=2000)
            await self._apply_stmt_timeout(session, timeout_ms=5000)

            repo = UserRepository(session)
            try:
                created = await repo.add(user)
                log.info("Users.add ← usuario creado (id=%s)", getattr(created, "user_id", None))
                return created
            except Exception as e:
                log.error("Users.add ERROR: %s", e)
                raise

    async def save(self, user: AppUser) -> AppUser:
        """
        Actualiza un usuario existente. El commit y refresh se delegan al repositorio.
        """
        async with self._session_scope() as session:
            await self._ping_db(session, timeout_ms=2000)
            await self._apply_stmt_timeout(session, timeout_ms=5000)

            repo = UserRepository(session)
            try:
                updated = await repo.save(user)
                log.info("Users.save ← usuario actualizado (id=%s)", getattr(updated, "user_id", None))
                return updated
            except Exception as e:
                log.error("Users.save ERROR: %s", e)
                raise

    async def set_status(self, user: AppUser, status: UserStatus) -> AppUser:
        """
        Cambia el estatus lógico del usuario y persiste el cambio.
        """
        async with self._session_scope() as session:
            await self._ping_db(session, timeout_ms=2000)
            await self._apply_stmt_timeout(session, timeout_ms=5000)

            repo = UserRepository(session)
            try:
                updated = await repo.set_status(user, status)
                log.info(
                    "Users.set_status ← usuario %s ahora en estado %s",
                    getattr(updated, "user_id", None),
                    status,
                )
                return updated
            except Exception as e:
                log.error("Users.set_status ERROR: %s", e)
                raise

    # -------------------------- Helpers de estado ---------------------------

    async def is_active(self, user: AppUser) -> bool:
        """
        Verifica si el usuario está activo según UserStatus.
        """
        status_value = getattr(user, "user_status", None)
        if status_value is None:
            # Fallback: si no hay campo de estado, asumimos activo
            return True
        try:
            return status_value == UserStatus.active
        except Exception:
            # En caso de que user_status no sea un enum pero sí un str/int compatible
            return str(status_value) == getattr(UserStatus.active, "value", "active")


# ---------------------- Helper retro-compatible ----------------------


async def get_current_user_from_token(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_async_session),
) -> AppUser:
    """
    Decodifica el JWT, recupera el usuario y valida que esté activo.
    Mantiene compatibilidad con código legado que dependía de este helper.
    """
    try:
        payload = decode_access_token(token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
        ) from e

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token sin 'sub'")

    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado")

    # Checamos flag de actividad (si existe)
    if hasattr(user, "is_active") and not getattr(user, "is_active"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no autorizado")

    return user


__all__ = ["UserService", "get_current_user_from_token"]

# Fin del script backend/app/modules/auth/services/user_service.py




