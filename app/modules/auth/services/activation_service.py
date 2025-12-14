
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/activation_service.py

Gestión de tokens de activación: emisión, expiración, activación de cuentas y
validaciones auxiliares. Alineado con la tabla public.account_activations y con
AuthService para orquestar el flujo completo.

Refactor Fase 3:
- Usa ActivationRepository para persistencia.
- Usa UserRepository (vía helper interno) para obtener/actualizar al usuario.
- Normaliza user_id a entero antes de insertar en account_activations.
- Integra CreditService.ensure_welcome_credits para asignar créditos de
  bienvenida al activar una cuenta por primera vez.

Autor: Ixchel Beristain
Actualizado: 2025-11-20
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Union

from sqlalchemy import update, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.enums import ActivationStatus, UserStatus
from app.modules.auth.models.activation_models import AccountActivation
from app.modules.auth.models.user_models import AppUser as User
from app.modules.auth.repositories import ActivationRepository, UserRepository
from app.modules.payments.services.credit_service import CreditService

logger = logging.getLogger(__name__)


class ActivationService:
    """
    Servicio de activación de cuentas:
      - Generación de tokens de activación.
      - Validación de tokens.
      - Activación de usuarios.
      - Asignación de créditos de bienvenida (welcome_credits) al activar
        por primera vez.
    """

    def __init__(self, db: AsyncSession, welcome_credits: int = 5) -> None:
        self.db = db
        self.activation_repo = ActivationRepository(db)
        self.user_repo = UserRepository(db)
        # Servicio de créditos (trabaja con user_id entero/BIGINT)
        self.credit_service = CreditService(db)
        # Créditos de bienvenida (configurable, por defecto 5)
        self.welcome_credits = welcome_credits

    # ----------------------- emisión de tokens -----------------------

    async def issue_activation_token(
        self,
        user_id: Union[int, str],
        *,
        ttl_minutes: int = 60 * 24,
        token_factory: Optional[callable] = None,
    ) -> str:
        """
        Emite un token de activación nuevo para el usuario.
        """
        # Normalizar user_id a entero, ya que account_activations.user_id es INTEGER/BIGINT.
        try:
            uid_int = int(user_id)
        except (TypeError, ValueError):
            raise ValueError(f"user_id inválido para token de activación: {user_id!r}")

        now = datetime.now(timezone.utc)
        expiration = now + timedelta(minutes=ttl_minutes)

        if token_factory is None:
            import secrets

            token_factory = lambda: secrets.token_urlsafe(32)  # pragma: no cover

        token = token_factory()

        # Creamos registro vía repositorio (centraliza la lógica de commit).
        await self.activation_repo.create_activation(
            user_id=uid_int,
            token=token,
            expires_at=expiration,
        )

        return token

    # ------------------------ activación ------------------------

    async def activate_account(self, token: str) -> Dict[str, Any]:
        """
        Intenta activar la cuenta asociada a un token de activación.

        Retorna dict con code/message/credits_assigned:
          - ACCOUNT_ACTIVATED
          - ALREADY_ACTIVATED
          - TOKEN_INVALID
          - TOKEN_EXPIRED
        """
        now = datetime.now(timezone.utc)

        activation = await self.activation_repo.get_by_token(token)
        if activation is None:
            return {
                "code": "TOKEN_INVALID",
                "message": "Token de activación inválido.",
                "credits_assigned": 0,
            }

        # Ya usado
        if activation.status == ActivationStatus.used:
            user = await self._get_user(activation.user_id)
            if user and getattr(user, "user_is_activated", False):
                return {
                    "code": "ALREADY_ACTIVATED",
                    "message": "La cuenta ya se encontraba activada.",
                    "credits_assigned": 0,
                }
            return {
                "code": "TOKEN_INVALID",
                "message": "El token ya fue utilizado.",
                "credits_assigned": 0,
            }

        # Expirado (status o tiempo)
        if activation.status == ActivationStatus.expired or activation.expires_at <= now:
            if activation.status != ActivationStatus.expired:
                await self.db.execute(
                    update(AccountActivation)
                    .where(AccountActivation.id == activation.id)
                    .values(status=ActivationStatus.expired)
                )
                await self.db.flush()
            return {
                "code": "TOKEN_EXPIRED",
                "message": "El token de activación ha expirado.",
                "credits_assigned": 0,
            }

        # Si llegamos aquí, el token es "usable"
        user = await self._get_user(activation.user_id)
        if not user:
            # Inconsistencia: hay registro de activación pero no usuario
            await self.activation_repo.mark_as_used(activation)
            return {
                "code": "TOKEN_INVALID",
                "message": "Usuario asociado no encontrado.",
                "credits_assigned": 0,
            }

        # Si ya estaba activado, no intentamos reasignar créditos
        if getattr(user, "user_is_activated", False):
            await self.activation_repo.mark_as_used(activation)
            return {
                "code": "ALREADY_ACTIVATED",
                "message": "La cuenta ya se encontraba activada.",
                "credits_assigned": 0,
            }

        # ---------------------------------------------------------
        # 1) Activar usuario
        # ---------------------------------------------------------
        user.user_is_activated = True
        user.user_status = UserStatus.active
        await self.user_repo.save(user)
        await self.activation_repo.mark_as_used(activation)

        # ---------------------------------------------------------
        # 2) Asignar créditos de bienvenida (idempotente)
        # ---------------------------------------------------------
        credits_assigned = 0
        warnings = []

        # Capturamos user_id en una variable local para evitar accesos perezosos
        # al ORM dentro del bloque de excepción (previene MissingGreenlet).
        try:
            user_id = int(user.user_id)
        except Exception:
            user_id = getattr(user, "user_id", None)

        try:
            if self.welcome_credits > 0 and user_id is not None:
                created = await self.credit_service.ensure_welcome_credits(
                    user_id=user_id,
                    welcome_credits=self.welcome_credits,
                )
                if created:
                    credits_assigned = self.welcome_credits
        except Exception as e:
            # No rompemos la activación si hay un problema con créditos
            # pero sí reportamos el warning a la UI
            logger.error(
                "Error asignando créditos de bienvenida al usuario %s: %s",
                user_id,
                e,
                exc_info=True,
            )
            warnings.append("welcome_credits_failed")

        result = {
            "code": "ACCOUNT_ACTIVATED",
            "message": "La cuenta se activó exitosamente.",
            "credits_assigned": credits_assigned,
        }
        
        if warnings:
            result["warnings"] = warnings
        
        return result

    # ------------------------ helpers internos ------------------------

    async def _get_user(self, user_id: Any) -> Optional[User]:
        """
        Helper simple para obtener al usuario sin acoplar a rutas.
        """
        # Usamos UserRepository para mantener la capa de acceso a datos
        try:
            return await self.user_repo.get_by_id(user_id)
        except Exception:
            # Fallback directo si algo sale mal con el repo
            res = await self.db.execute(select(User).where(User.user_id == user_id))
            return res.scalar_one_or_none()

    async def is_active(self, user: User) -> bool:
        """
        Indica si la cuenta del usuario está activada, combinando:
        - Flag lógico user_is_activated (si existe)
        - Estado del usuario (UserStatus)
        """
        flag = getattr(user, "user_is_activated", None)
        if flag is not None:
            return bool(flag)

        status = getattr(user, "user_status", None)
        if status is None:
            # Fallback conservador: si no hay campo, consideramos activo
            return True

        try:
            return status == UserStatus.active
        except Exception:
            return str(status) == getattr(UserStatus.active, "value", "active")


__all__ = ["ActivationService"]

# Fin del script backend/app/modules/auth/services/activation_service.py

