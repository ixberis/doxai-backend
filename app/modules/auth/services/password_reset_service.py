
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/password_reset_service.py

Flujo de restablecimiento de contraseña:
- Inicio de proceso (solicitud de reset).
- Confirmación de reset (nuevo password).
- Validación de tokens de reset.

Refactor Fase 3:
- Usa PasswordResetRepository para persistir tokens de reset.
- Se apoya en UserService para obtener/actualizar al usuario.
- EmailSender se inicializa vía EmailSender.from_env(), usando el método
  específico send_password_reset_email() (compatible con StubEmailSender).

Autor: Ixchel Beristain
Actualizado: 2025-11-19
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.repositories import PasswordResetRepository
from app.modules.auth.services.user_service import UserService
from app.shared.integrations.email_sender import EmailSender
from app.shared.config.config_loader import get_settings


class PasswordResetService:
    """
    Servicio de restablecimiento de contraseña.

    Responsabilidades:
      - Generar y persistir tokens de reset.
      - Enviar correos de restablecimiento.
      - Validar tokens y aplicar la nueva contraseña.
    """

    def __init__(
        self,
        db: AsyncSession,
        email_sender: Optional[EmailSender] = None,
        token_factory: Optional[callable] = None,
    ) -> None:
        self.db = db
        self.settings = get_settings()
        self.reset_repo = PasswordResetRepository(db)
        self.user_service = UserService.with_session(db)
        # IMPORTANTE: usar la API real de EmailSender (from_env)
        self.email_sender = email_sender or EmailSender.from_env()
        self._token_factory = token_factory

    # --------------------- inicio de proceso ---------------------

    async def start_password_reset(self, user_email: str) -> Dict[str, Any]:
        """
        Inicia el proceso de restablecimiento:
        - Localiza al usuario por email.
        - Genera token de reset.
        - Lo persiste vía repositorio.
        - Envía correo de instrucciones (si el usuario existe).

        Siempre devuelve un mensaje genérico para no revelar existencia de cuentas.
        """
        user = await self.user_service.get_by_email(user_email)
        if not user:
            # Seguridad: respondemos igual aunque el usuario no exista.
            return {
                "code": "RESET_STARTED",
                "message": "Si el correo está registrado, se enviaron instrucciones.",
            }

        # Generamos token
        token = await self._generate_token(str(user.user_id))

        # Persistimos token
        ttl_minutes = getattr(self.settings, "AUTH_PASSWORD_RESET_TTL_MINUTES", 60)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
        await self.reset_repo.create_reset(
            user_id=user.user_id,
            token=token,
            expires_at=expires_at,
        )

        # Enviamos correo usando el método específico de EmailSender,
        # compatible con StubEmailSender (to_email, full_name, reset_token)
        await self._send_reset_email(user.user_email, token)

        return {
            "code": "RESET_STARTED",
            "message": "Si el correo está registrado, se enviaron instrucciones.",
        }

    # --------------------- confirmación de reset ---------------------

    async def confirm_password_reset(self, token: str, new_password_hash: str) -> Dict[str, Any]:
        """
        Confirma el restablecimiento usando un token válido.

        Args:
            token: Token de reset proveído por el usuario.
            new_password_hash: Contraseña ya hasheada.

        Returns:
            Dict con:
                - code: "PASSWORD_RESET_OK" o "TOKEN_INVALID"
                - message: texto explicativo
        """
        now = datetime.now(timezone.utc)
        reset = await self.reset_repo.get_by_token(token, only_valid=True, now=now)
        if reset is None:
            return {
                "code": "TOKEN_INVALID",
                "message": "El token de restablecimiento es inválido o ha expirado.",
            }

        user = await self.user_service.get_by_id(reset.user_id)
        if not user:
            await self.reset_repo.mark_as_used(reset)
            return {
                "code": "TOKEN_INVALID",
                "message": "Usuario asociado al token no encontrado.",
            }

        # Actualizamos password y marcamos token como usado
        # Campo correcto en AppUser es user_password_hash
        user.user_password_hash = new_password_hash
        await self.user_service.save(user)
        await self.reset_repo.mark_as_used(reset)

        return {
            "code": "PASSWORD_RESET_OK",
            "message": "La contraseña se actualizó correctamente.",
        }

    # --------------------- helpers internos ---------------------

    async def _generate_token(self, user_id: str) -> str:
        """
        Genera un token de reset. Por defecto usa secrets.token_urlsafe.
        Se permite inyectar un token_factory para pruebas.
        """
        if self._token_factory is not None:
            return self._token_factory(user_id)

        import secrets

        return secrets.token_urlsafe(32)

    async def _send_reset_email(self, email: str, token: str) -> None:
        """
        Envía el correo de restablecimiento usando EmailSender.

        En modo stub, esto se imprime en consola como:
        [CONSOLE EMAIL] Password reset → email | token=...
        """
        # Algunos adaptadores reales podrían necesitar también la URL,
        # pero el StubEmailSender solo acepta (to_email, full_name, reset_token).
        await self.email_sender.send_password_reset_email(
            to_email=email,
            full_name="",
            reset_token=token,
        )


__all__ = ["PasswordResetService"]

# Fin del script backend/app/modules/auth/services/password_reset_service.py
