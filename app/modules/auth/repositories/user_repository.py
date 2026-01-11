
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

from datetime import datetime, timezone
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import func, select, update
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
        Obtiene un usuario por su identificador interno (PK INT).
        Devuelve None si no existe.
        """
        stmt = select(AppUser).where(AppUser.user_id == user_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_auth_user_id(self, auth_user_id: UUID) -> Optional[AppUser]:
        """
        Obtiene un usuario por auth_user_id (UUID SSOT).
        Este es el método preferido para resolver usuarios desde JWT sub.
        Devuelve None si no existe.
        """
        stmt = select(AppUser).where(AppUser.auth_user_id == auth_user_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
    
    # ─────────────────────────────────────────────────────────────────────────
    # get_by_auth_user_id_core_ctx: Versión Core MÍNIMA para auth dependencies
    # ─────────────────────────────────────────────────────────────────────────
    async def get_by_auth_user_id_core_ctx(
        self, auth_user_id: UUID
    ) -> tuple[Optional["AuthContextDTO"], dict]:
        """
        Obtiene contexto de usuario por auth_user_id usando Core SQL MÍNIMO.
        Optimizado para dependencies de autenticación (get_current_user).
        
        Solo 1 statement, sin ORM, sin eager loading.
        Devuelve AuthContextDTO con solo los campos necesarios para auth.
        
        Args:
            auth_user_id: UUID del usuario
            
        Returns:
            Tupla (AuthContextDTO o None, timings_dict)
        """
        import time
        from sqlalchemy import text
        from app.modules.auth.schemas.auth_context_dto import AuthContextDTO
        from app.shared.queries.auth_lookup import AUTH_LOOKUP_SQL
        
        timings: dict = {}
        
        # Usa constante exportable para facilitar testing
        core_sql = text(AUTH_LOOKUP_SQL.strip())
        
        t_exec_start = time.perf_counter()
        result = await self._db.execute(core_sql, {"auth_user_id": auth_user_id})
        t_exec_end = time.perf_counter()
        timings["execute_ms"] = (t_exec_end - t_exec_start) * 1000
        
        t_fetch_start = time.perf_counter()
        row_mapping = result.mappings().first()
        t_fetch_end = time.perf_counter()
        timings["fetch_ms"] = (t_fetch_end - t_fetch_start) * 1000
        
        t_consume_start = time.perf_counter()
        dto = AuthContextDTO.from_mapping(dict(row_mapping)) if row_mapping else None
        t_consume_end = time.perf_counter()
        timings["consume_ms"] = (t_consume_end - t_consume_start) * 1000
        
        timings["total_ms"] = timings["execute_ms"] + timings["fetch_ms"] + timings["consume_ms"]
        
        return dto, timings

    # ─────────────────────────────────────────────────────────────────────────
    # get_by_email: Versión ORM (producción)
    # ─────────────────────────────────────────────────────────────────────────
    async def get_by_email(self, email: str) -> Optional[AppUser]:
        """
        Obtiene un usuario por email usando ORM.
        Usa comparación directa para aprovechar índice CITEXT (case-insensitive).
        
        Args:
            email: Email del usuario a buscar
            
        Returns:
            AppUser o None
        """
        norm_email = (email or "").strip().lower()
        if not norm_email:
            return None

        stmt = select(AppUser).where(AppUser.user_email == norm_email)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
    
    # ─────────────────────────────────────────────────────────────────────────
    # get_by_email_core_login: Versión Core MÍNIMA para login (1 statement)
    # ─────────────────────────────────────────────────────────────────────────
    async def get_by_email_core_login(self, email: str) -> Optional["LoginUserDTO"]:
        """
        Obtiene usuario por email usando Core SQL MÍNIMO para login.
        Solo 1 statement, sin ORM, sin eager loading.
        
        Columnas seleccionadas:
        - user_id, auth_user_id: identificación
        - user_email, user_password_hash: validación de credenciales
        - user_role, user_status: información de cuenta
        - user_is_activated, deleted_at: estado de activación
        - user_full_name: para response de login
        
        Args:
            email: Email del usuario a buscar
            
        Returns:
            LoginUserDTO o None
        """
        from sqlalchemy import text
        from app.modules.auth.schemas.login_user_dto import LoginUserDTO
        
        norm_email = (email or "").strip().lower()
        if not norm_email:
            return None

        # SQL mínimo: solo columnas necesarias para login + AND deleted_at IS NULL
        core_sql = text("""
            SELECT
                user_id,
                auth_user_id,
                user_email,
                user_password_hash,
                user_role,
                user_status,
                user_is_activated,
                deleted_at,
                user_full_name
            FROM public.app_users
            WHERE user_email = :email
              AND deleted_at IS NULL
            LIMIT 1
        """)
        
        result = await self._db.execute(core_sql, {"email": norm_email})
        row_mapping = result.mappings().first()
        
        if row_mapping:
            return LoginUserDTO.from_mapping(dict(row_mapping))
        return None
    
    # ─────────────────────────────────────────────────────────────────────────
    # get_by_email_core: Versión Core completa (para diagnóstico A/B)
    # ─────────────────────────────────────────────────────────────────────────
    async def get_by_email_core(self, email: str) -> Optional["UserDTO"]:
        """
        Obtiene un usuario por email usando SQLAlchemy Core (sin ORM).
        Devuelve UserDTO en lugar de AppUser para evitar overhead ORM.
        
        NOTA: Para login, usar get_by_email_core_login() que es más eficiente.
        
        Args:
            email: Email del usuario a buscar
            
        Returns:
            UserDTO o None
        """
        from sqlalchemy import text
        from app.modules.auth.schemas.user_dto import UserDTO
        
        norm_email = (email or "").strip().lower()
        if not norm_email:
            return None

        # SQL corregido: user_full_name (no user_name) + deleted_at IS NULL
        core_sql = text("""
            SELECT user_id, auth_user_id, user_email, user_full_name, user_password_hash, 
                   user_status, user_created_at, user_updated_at, deleted_at,
                   welcome_email_status, welcome_email_sent_at, welcome_email_attempts,
                   welcome_email_claimed_at, welcome_email_last_error
            FROM public.app_users 
            WHERE user_email = :email
              AND deleted_at IS NULL
            LIMIT 1
        """)
        
        result = await self._db.execute(core_sql, {"email": norm_email})
        row_mapping = result.mappings().first()
        
        if row_mapping:
            return UserDTO.from_mapping(dict(row_mapping))
        return None
    
    # ─────────────────────────────────────────────────────────────────────────
    # get_by_email_timed: Versión con instrumentación A/B (solo diagnóstico)
    # ─────────────────────────────────────────────────────────────────────────
    async def get_by_email_timed(
        self, 
        email: str, 
        *, 
        use_core: bool = False,
    ) -> tuple[Optional[AppUser] | Optional["UserDTO"], dict]:
        """
        Versión instrumentada para diagnóstico A/B.
        NO usar en producción - solo para endpoints internos de diagnóstico.
        
        Args:
            email: Email del usuario a buscar
            use_core: Si True, usa Core mode (devuelve UserDTO)
            
        Returns:
            Tupla (user|DTO o None, timings_dict)
        """
        import time
        import logging
        from sqlalchemy import text
        from app.modules.auth.schemas.user_dto import UserDTO
        
        logger = logging.getLogger(__name__)
        
        # NOTA: El conteo de statements se hace en el endpoint (counter delta global)
        # para evitar doble conteo. Este método solo retorna timings de ejecución.
        timings: dict = {
            "mode": "core" if use_core else "orm",
        }
        
        norm_email = (email or "").strip().lower()
        if not norm_email:
            return None, {"execute_ms": 0, "fetch_ms": 0, "consume_ms": 0, "total_ms": 0, "mode": timings["mode"]}

        if use_core:
            # ─── MODO CORE ───
            # SQL corregido: user_full_name (no user_name) + deleted_at IS NULL
            core_sql = text("""
                SELECT user_id, auth_user_id, user_email, user_full_name, user_password_hash, 
                       user_status, user_created_at, user_updated_at, deleted_at,
                       welcome_email_status, welcome_email_sent_at, welcome_email_attempts,
                       welcome_email_claimed_at, welcome_email_last_error
                FROM public.app_users 
                WHERE user_email = :email
                  AND deleted_at IS NULL
                LIMIT 1
            """)
            
            if logger.isEnabledFor(logging.DEBUG):
                masked_email = norm_email[:3] + "***" if len(norm_email) > 3 else "***"
                logger.debug("repo.get_by_email_timed CORE | email=%s", masked_email)
            
            t_exec_start = time.perf_counter()
            result = await self._db.execute(core_sql, {"email": norm_email})
            t_exec_end = time.perf_counter()
            timings["execute_ms"] = (t_exec_end - t_exec_start) * 1000
            
            t_fetch_start = time.perf_counter()
            row_mapping = result.mappings().first()
            t_fetch_end = time.perf_counter()
            timings["fetch_ms"] = (t_fetch_end - t_fetch_start) * 1000
            
            t_consume_start = time.perf_counter()
            user = UserDTO.from_mapping(dict(row_mapping)) if row_mapping else None
            t_consume_end = time.perf_counter()
            timings["consume_ms"] = (t_consume_end - t_consume_start) * 1000
            
        else:
            # ─── MODO ORM ───
            stmt = select(AppUser).where(AppUser.user_email == norm_email)
            
            if logger.isEnabledFor(logging.DEBUG):
                masked_email = norm_email[:3] + "***" if len(norm_email) > 3 else "***"
                logger.debug("repo.get_by_email_timed ORM | email=%s", masked_email)
            
            t_exec_start = time.perf_counter()
            result = await self._db.execute(stmt)
            t_exec_end = time.perf_counter()
            timings["execute_ms"] = (t_exec_end - t_exec_start) * 1000
            
            t_fetch_start = time.perf_counter()
            user = result.scalar_one_or_none()
            t_fetch_end = time.perf_counter()
            timings["fetch_ms"] = (t_fetch_end - t_fetch_start) * 1000
            
            timings["consume_ms"] = 0.0
        
        # NOTA: statements_executed se calcula en el endpoint (counter delta global)
        # Aquí solo calculamos total_ms
        timings["total_ms"] = timings["execute_ms"] + timings["fetch_ms"] + timings["consume_ms"]
        
        return user, timings

    # ─────────────────────────────────────────────────────────────────────────
    # set_auth_user_id_if_missing: Fix SSOT legacy para usuarios sin UUID
    # ─────────────────────────────────────────────────────────────────────────
    async def set_auth_user_id_if_missing(self, user_id: int, new_uuid: "UUID") -> bool:
        """
        Persiste auth_user_id para usuarios legacy que no lo tienen.
        
        SQL:
            UPDATE public.app_users 
            SET auth_user_id = :uuid 
            WHERE user_id = :id AND auth_user_id IS NULL
        
        Args:
            user_id: PK del usuario
            new_uuid: UUID a asignar
            
        Returns:
            True si se actualizó 1 fila, False si ya tenía UUID o no existe
        """
        from sqlalchemy import text
        from uuid import UUID
        
        stmt = text("""
            UPDATE public.app_users 
            SET auth_user_id = :new_uuid 
            WHERE user_id = :user_id 
              AND auth_user_id IS NULL
        """)
        
        result = await self._db.execute(stmt, {"new_uuid": new_uuid, "user_id": user_id})
        # NO commit aquí - el caller maneja la transacción
        
        return result.rowcount == 1

    async def exists_by_email(self, email: str) -> bool:
        """
        Indica si ya existe un usuario con el email dado.
        Usa EXISTS para cortar en el primer match (más eficiente que COUNT).
        Útil para validaciones de registro.
        """
        norm_email = (email or "").strip().lower()  # Higiene de input
        if not norm_email:
            return False

        # EXISTS corta en primer match, aprovecha índice CITEXT
        stmt = select(select(1).where(AppUser.user_email == norm_email).exists())
        result = await self._db.execute(stmt)
        return bool(result.scalar())

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

    async def claim_welcome_email_if_pending(
        self,
        user_id: int,
        stale_ttl_minutes: int = 15,
    ) -> tuple[bool, int]:
        """
        Claim atómico para envío de welcome email (anti-race + anti-stuck).

        Ejecuta:
            UPDATE app_users
            SET welcome_email_status = 'pending',
                welcome_email_claimed_at = now(),
                welcome_email_attempts = welcome_email_attempts + 1,
                welcome_email_last_error = NULL  -- limpia error previo
            WHERE user_id = :user_id
              AND (
                welcome_email_status IS NULL
                OR (welcome_email_status = 'pending' 
                    AND welcome_email_claimed_at < now() - (:ttl_minutes * interval '1 minute'))
              )

        Retorna tupla (claimed: bool, attempts: int).
        - claimed=True si este proceso ganó la carrera
        - attempts es el nuevo contador después del claim

        Importante: NO hace commit; el servicio maneja la transacción.
        """
        from sqlalchemy import text
        
        # UPDATE con reclaim de pending stale (parámetros seguros, schema explícito)
        stmt = text("""
            UPDATE public.app_users
            SET welcome_email_status = 'pending',
                welcome_email_claimed_at = now(),
                welcome_email_attempts = welcome_email_attempts + 1,
                welcome_email_last_error = NULL
            WHERE user_id = :user_id
              AND (
                welcome_email_status IS NULL
                OR (
                    welcome_email_status = 'pending'
                    AND welcome_email_claimed_at < now() - (:ttl_minutes * interval '1 minute')
                )
              )
            RETURNING welcome_email_attempts
        """)
        
        result = await self._db.execute(
            stmt,
            {"user_id": user_id, "ttl_minutes": stale_ttl_minutes},
        )
        row = result.fetchone()
        
        if row:
            return (True, row[0])
        return (False, 0)

    async def mark_welcome_email_sent(self, user_id: int) -> None:
        """
        Marca el correo como enviado exitosamente.
        Llamar después de enviar el correo.
        """
        stmt = (
            update(AppUser)
            .where(AppUser.user_id == user_id)
            .values(
                welcome_email_status="sent",
                welcome_email_sent_at=datetime.now(timezone.utc),
                welcome_email_last_error=None,
            )
        )
        await self._db.execute(stmt)
        # NO commit aquí

    async def mark_welcome_email_failed(self, user_id: int, error: str) -> None:
        """
        Marca el correo como fallido con mensaje de error.
        Permite reintentos manuales posteriores.
        """
        stmt = (
            update(AppUser)
            .where(AppUser.user_id == user_id)
            .values(
                welcome_email_status="failed",
                welcome_email_last_error=error[:500] if error else "Unknown error",
            )
        )
        await self._db.execute(stmt)
        # NO commit aquí


__all__ = ["UserRepository"]

# Fin del archivo backend/app/modules/auth/repositories/user_repository.py
