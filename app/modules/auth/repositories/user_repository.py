
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
    # get_by_email_core: Versión Core (para login optimizado)
    # ─────────────────────────────────────────────────────────────────────────
    async def get_by_email_core(self, email: str) -> Optional["UserDTO"]:
        """
        Obtiene un usuario por email usando SQLAlchemy Core (sin ORM).
        Devuelve UserDTO en lugar de AppUser para evitar overhead ORM.
        
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

        core_sql = text("""
            SELECT user_id, auth_user_id, user_email, user_name, user_password_hash, 
                   user_status, user_created_at, user_updated_at, deleted_at,
                   welcome_email_status, welcome_email_sent_at, welcome_email_attempts,
                   welcome_email_claimed_at, welcome_email_last_error
            FROM public.app_users 
            WHERE user_email = :email
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
        from app.shared.database.statement_counter import get_counter
        
        logger = logging.getLogger(__name__)
        
        timings: dict = {
            "mode": "core" if use_core else "orm",
            "statements_executed": 0,
        }
        
        norm_email = (email or "").strip().lower()
        if not norm_email:
            return None, {"execute_ms": 0, "fetch_ms": 0, "consume_ms": 0, "total_ms": 0, "mode": timings["mode"], "statements_executed": 0}

        # Capturar contador antes de ejecutar
        counter_before = get_counter()
        count_start = counter_before.count if counter_before else 0
        
        if use_core:
            # ─── MODO CORE ───
            core_sql = text("""
                SELECT user_id, auth_user_id, user_email, user_name, user_password_hash, 
                       user_status, user_created_at, user_updated_at, deleted_at,
                       welcome_email_status, welcome_email_sent_at, welcome_email_attempts,
                       welcome_email_claimed_at, welcome_email_last_error
                FROM public.app_users 
                WHERE user_email = :email
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
        
        # Capturar contador después
        counter_after = get_counter()
        count_end = counter_after.count if counter_after else 0
        timings["statements_executed"] = count_end - count_start
        
        timings["total_ms"] = timings["execute_ms"] + timings["fetch_ms"] + timings["consume_ms"]
        
        return user, timings

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
