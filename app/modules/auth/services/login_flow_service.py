# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/login_flow_service.py

Flujo de login y refresh de tokens:
- Aplica rate limiting con RateLimitService (single source of truth).
- Valida credenciales.
- Verifica activación de cuenta.
- Emite tokens de acceso/refresh.
- Refresca tokens.
- Progressive backoff for failed attempts.

Autor: Ixchel Beristain
Fecha: 19/11/2025
Updated: 18/12/2025 - Unified lockout with RateLimitService
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Mapping

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.services.user_service import UserService
from app.modules.auth.services.activation_service import ActivationService
from app.modules.auth.services.audit_service import AuditService
from app.modules.auth.services.token_issuer_service import TokenIssuerService
from app.modules.auth.utils.payload_extractors import as_dict
from app.shared.utils.security import verify_password
from app.shared.utils.jwt_utils import verify_token_type
from app.shared.security.rate_limit_service import get_rate_limiter
from app.shared.security.rate_limit_dep import RateLimitExceeded

logger = logging.getLogger(__name__)


# Progressive backoff delays (seconds) based on attempt count
BACKOFF_DELAYS = [0, 0.2, 0.4, 0.8, 1.2, 2.0]  # Max 2 seconds


def _get_backoff_delay(attempt_count: int) -> float:
    """Calculate backoff delay based on attempt count."""
    if attempt_count < len(BACKOFF_DELAYS):
        return BACKOFF_DELAYS[attempt_count]
    return BACKOFF_DELAYS[-1]  # Max delay


class LoginFlowService:
    """
    Orquestador del login y refresh de tokens.
    
    Uses RateLimitService as single source of truth for:
    - Rate limiting by IP (20/5min)
    - Lockout by email (5/15min)
    - Progressive backoff calculation
    """

    def __init__(
        self,
        db: AsyncSession,
        token_issuer: TokenIssuerService | None = None,
    ) -> None:
        self.db = db
        self.user_service = UserService.with_session(db)
        self.activation_service = ActivationService(db)
        self.token_issuer = token_issuer or TokenIssuerService()
        self._rate_limiter = get_rate_limiter()

    async def _apply_backoff(self, ip_address: str, email: str) -> None:
        """Apply progressive backoff delay based on failed attempt count."""
        # Get attempt count from rate limiter
        attempt_count = self._rate_limiter.get_attempt_count(
            endpoint="auth:login",
            key_type="email",
            identifier=email,
        )
        
        delay = _get_backoff_delay(attempt_count)
        if delay > 0:
            logger.debug(f"Applying backoff delay: {delay}s for email={email[:4]}***")
            await asyncio.sleep(delay)

    async def login(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        """
        Autentica al usuario y retorna tokens.

        data esperado:
            - email
            - password
            - recaptcha_token (ya validado antes por AuthService)
            - ip_address
            - user_agent
        """
        payload = as_dict(data)
        email = (payload.get("email") or "").strip().lower()
        password = payload.get("password", "")
        ip_address = payload.get("ip_address", "unknown")
        user_agent = payload.get("user_agent")

        if not email or not password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email y contraseña son obligatorios.",
            )

        # Rate limiting using RateLimitService as single source of truth
        # Check email lockout (5/15min window)
        email_result = self._rate_limiter.check_and_consume(
            endpoint="auth:login",
            key_type="email",
            identifier=email,
        )
        if not email_result.allowed:
            AuditService.log_login_blocked(email=email, ip_address=ip_address)
            raise RateLimitExceeded(
                retry_after=email_result.retry_after,
                detail="Demasiados intentos de inicio de sesión. Intente más tarde.",
            )

        # Apply progressive backoff before checking credentials
        await self._apply_backoff(ip_address, email)

        # Buscar usuario
        user = await self.user_service.get_by_email(email)
        if not user:
            # Already consumed one attempt above, just audit
            AuditService.log_login_failed(
                email=email,
                ip_address=ip_address,
                reason="Usuario no encontrado",
                user_agent=user_agent,
            )
            # Generic message to not reveal if user exists
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales inválidas.",
            )

        # Obtener hash de contraseña desde el modelo actual
        password_hash = getattr(user, "user_password_hash", None)
        if password_hash is None:
            # Fallback por compatibilidad con modelos antiguos
            password_hash = getattr(user, "password_hash", None)

        if password_hash is None:
            logger.error(
                "LOGIN: usuario %s (%s) no tiene campo de hash de contraseña (user_password_hash/password_hash).",
                getattr(user, "user_id", None),
                email,
            )
            AuditService.log_login_failed(
                email=email,
                ip_address=ip_address,
                reason="Configuración de usuario inválida (sin hash de contraseña)",
                user_agent=user_agent,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Configuración de usuario inválida.",
            )

        # Verificar contraseña
        if not verify_password(password, password_hash):
            # Already consumed one attempt above, just audit
            AuditService.log_login_failed(
                email=email,
                ip_address=ip_address,
                reason="Contraseña incorrecta",
                user_agent=user_agent,
            )
            # Generic message
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales inválidas.",
            )

        # Verificar activación
        if not await self.activation_service.is_active(user):
            AuditService.log_login_failed(
                email=email,
                ip_address=ip_address,
                reason="Cuenta no activada",
                user_agent=user_agent,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="La cuenta aún no ha sido activada.",
            )

        # Login exitoso - reset rate limit counters
        self._reset_rate_limit_counters(ip_address, email)
        
        AuditService.log_login_success(
            user_id=str(user.user_id),
            email=user.user_email,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        tokens = self.token_issuer.issue_tokens_for_user(user_id=str(user.user_id))

        # Construir respuesta alineada con LoginResponse (schemas)
        return {
            "message": "Login exitoso.",
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": "bearer",
            "user": {
                "user_id": str(user.user_id),
                "user_email": user.user_email,
                "user_full_name": user.user_full_name,
                "user_role": getattr(user, "user_role", None),
                "user_status": getattr(user, "user_status", None),
            },
        }

    def _reset_rate_limit_counters(self, ip_address: str, email: str) -> None:
        """Reset rate limit counters on successful login."""
        try:
            self._rate_limiter.reset_key("auth:login", "email", email)
            self._rate_limiter.reset_key("auth:login", "ip", ip_address)
        except Exception as e:
            logger.warning(f"Failed to reset rate limit counters: {e}")

    async def refresh_tokens(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        """
        Refresca tokens de acceso a partir de un refresh_token válido.

        data esperado:
            - refresh_token
        """
        payload = as_dict(data)
        refresh_token = payload.get("refresh_token")

        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Refresh token requerido.",
            )

        # Validar refresh token usando helper de jwt_utils
        token_payload = verify_token_type(refresh_token, expected_type="refresh")
        if not token_payload:
            logger.warning("Intento de refresh con token inválido o expirado")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido o expirado.",
            )

        user_id = token_payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token sin identificador de usuario.",
            )

        user = await self.user_service.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario no encontrado.",
            )
        if not await self.activation_service.is_active(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario inactivo o no activado.",
            )

        tokens = self.token_issuer.issue_tokens_for_user(user_id=str(user.user_id))

        AuditService.log_refresh_token_success(
            user_id=str(user.user_id),
        )

        # El schema de TokenResponse probablemente NO espera message, solo tokens
        return {
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": "bearer",
        }


__all__ = ["LoginFlowService"]

# Fin del script backend/app/modules/auth/services/login_flow_service.py
