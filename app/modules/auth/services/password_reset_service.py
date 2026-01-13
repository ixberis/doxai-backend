
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
Actualizado: 2025-12-20
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from uuid import UUID

from app.modules.auth.repositories import PasswordResetRepository
from app.modules.auth.services.user_service import UserService
from app.shared.integrations.email_sender import EmailSender
from app.shared.config.config_loader import get_settings

logger = logging.getLogger(__name__)


def _mask_email(email: str) -> str:
    """Enmascara email para logging seguro: us***@dom***.com"""
    e = (email or "").strip().lower()
    if not e or "@" not in e:
        return "***@***.***"
    local, domain = e.split("@", 1)
    masked_local = f"{local[:2]}***" if len(local) >= 2 else "***"
    if "." in domain:
        dom_parts = domain.rsplit(".", 1)
        masked_domain = f"{dom_parts[0][:3]}***.{dom_parts[1]}"
    else:
        masked_domain = f"{domain[:3]}***"
    return f"{masked_local}@{masked_domain}"


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
        # IMPORTANTE: pasar db para instrumentación de auth_email_events
        self.email_sender = email_sender or EmailSender.from_env(db_session=db)
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
        NUNCA lanza excepciones por fallos de email - siempre responde 200.
        """
        masked_email = _mask_email(user_email)
        
        user = await self.user_service.get_by_email(user_email)
        if not user:
            # Seguridad: respondemos igual aunque el usuario no exista.
            logger.info(
                "password_reset_started email=%s user_exists=false",
                masked_email,
            )
            return {
                "code": "RESET_STARTED",
                "message": "Si el correo está registrado, se enviaron instrucciones.",
            }

        user_id = user.user_id
        logger.info(
            "password_reset_started email=%s user_id=%s",
            masked_email,
            user_id,
        )

        # Generamos token
        token = await self._generate_token(str(user_id))

        # Persistimos token (siempre, incluso si el email falla después)
        ttl_minutes = getattr(self.settings, "AUTH_PASSWORD_RESET_TTL_MINUTES", 60)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
        reset_record = await self.reset_repo.create_reset(
            user_id=user_id,
            token=token,
            expires_at=expires_at,
        )

        # Enviamos correo - capturamos cualquier excepción para no romper el endpoint
        # DB 2.0 SSOT: Propagar auth_user_id para persistencia de eventos
        await self._send_reset_email_safely(
            email=user.user_email,
            token=token,
            reset_record=reset_record,
            user_id=user_id,
            auth_user_id=getattr(user, "auth_user_id", None),
        )

        return {
            "code": "RESET_STARTED",
            "message": "Si el correo está registrado, se enviaron instrucciones.",
        }

    # --------------------- confirmación de reset ---------------------

    async def confirm_password_reset(
        self,
        token: str,
        new_password_hash: str,
        *,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Confirma el restablecimiento usando un token válido.

        Args:
            token: Token de reset proveído por el usuario.
            new_password_hash: Contraseña ya hasheada.
            ip_address: IP desde donde se hizo el reset (opcional).
            user_agent: User agent del navegador (opcional).

        Returns:
            Dict con:
                - code: "PASSWORD_RESET_OK" o "TOKEN_INVALID"
                - message: texto explicativo
                - user_id: ID del usuario (solo si exitoso)
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
        old_email = user.user_email  # Para invalidación
        user.user_password_hash = new_password_hash
        await self.user_service.save(user)
        await self.reset_repo.mark_as_used(reset)
        
        # Invalidate login cache (password changed) - SSOT invalidation
        try:
            from app.shared.security.login_user_cache import invalidate_login_user_cache
            if old_email:
                await invalidate_login_user_cache(old_email)
        except Exception:
            pass  # Best-effort, silent

        user_id = str(user.user_id)
        user_email = user.user_email or ""
        user_name = getattr(user, "user_full_name", None) or getattr(user, "full_name", "") or ""

        # Log de éxito
        logger.info(
            "password_reset_success user_id=%s email=%s ip=%s",
            user_id,
            _mask_email(user_email),
            ip_address or "unknown",
        )

        # Enviar email de notificación (best-effort, no debe fallar el reset)
        # DB 2.0 SSOT: Propagar auth_user_id para persistencia de eventos
        await self._send_reset_success_email_safely(
            user_email=user_email,
            user_id=user_id,
            full_name=user_name,
            auth_user_id=getattr(user, "auth_user_id", None),
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {
            "code": "PASSWORD_RESET_OK",
            "message": "La contraseña se actualizó correctamente.",
            "user_id": user_id,
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

    async def _send_reset_email_safely(
        self,
        *,
        email: str,
        token: str,
        reset_record: Any,
        user_id: int,
        auth_user_id: Optional["UUID"] = None,
    ) -> None:
        """
        Envía el correo de restablecimiento de forma segura.
        Captura cualquier excepción y actualiza el tracking en DB.
        NUNCA lanza excepciones - el endpoint siempre responde 200.
        
        DB 2.0 SSOT: Propaga auth_user_id al sender para persistencia de eventos.
        """
        masked_email = _mask_email(email)
        
        try:
            await self.email_sender.send_password_reset_email(
                to_email=email,
                full_name="",
                reset_token=token,
                auth_user_id=auth_user_id,
            )
            
            # Éxito: actualizar tracking
            reset_record.reset_email_status = "sent"
            reset_record.reset_email_sent_at = datetime.now(timezone.utc)
            await self.db.commit()
            
            logger.info(
                "password_reset_email_sent email=%s user_id=%s auth_user_id=%s",
                masked_email,
                user_id,
                (str(auth_user_id)[:8] + "...") if auth_user_id else "None",
            )
            
        except Exception as e:
            # Fallo: actualizar tracking pero NO propagar excepción
            error_msg = str(e)[:500]
            
            try:
                reset_record.reset_email_status = "failed"
                reset_record.reset_email_attempts = (reset_record.reset_email_attempts or 0) + 1
                reset_record.reset_email_last_error = error_msg
                await self.db.commit()
            except Exception:
                # Si falla el commit, rollback para dejar sesión limpia
                await self.db.rollback()
            
            logger.error(
                "password_reset_email_failed email=%s user_id=%s error=%s",
                masked_email,
                user_id,
                error_msg,
            )

    async def _send_reset_success_email_safely(
        self,
        *,
        user_email: str,
        user_id: str,
        full_name: str,
        auth_user_id: Optional["UUID"] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """
        Envía email de notificación de reset exitoso (best-effort).
        No lanza excepciones; loguea warning en caso de fallo.
        
        DB 2.0 SSOT: Propaga auth_user_id al sender para persistencia de eventos.
        """
        if not user_email:
            logger.warning(
                "password_reset_success_email_skipped user_id=%s reason=no_email",
                user_id,
            )
            return

        reset_datetime = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        try:
            await self.email_sender.send_password_reset_success_email(
                to_email=user_email,
                full_name=full_name,
                ip_address=ip_address,
                user_agent=user_agent,
                reset_datetime_utc=reset_datetime,
                auth_user_id=auth_user_id,
            )
            logger.info(
                "password_reset_success_email_sent to=%s user_id=%s auth_user_id=%s",
                _mask_email(user_email),
                user_id,
                (str(auth_user_id)[:8] + "...") if auth_user_id else "None",
            )
        except Exception as e:
            logger.warning(
                "password_reset_success_email_failed to=%s user_id=%s auth_user_id=%s error=%s",
                _mask_email(user_email),
                user_id,
                (str(auth_user_id)[:8] + "...") if auth_user_id else "None",
                str(e)[:200],
            )


__all__ = ["PasswordResetService"]

# Fin del script backend/app/modules/auth/services/password_reset_service.py
