# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/login_flow_service.py

Flujo de login y refresh de tokens:
- Aplica rate limiting con RateLimitService (single source of truth).
- Valida credenciales.
- Verifica activación de cuenta.
- Emite tokens de acceso/refresh.
- Registra sesión en user_sessions para métricas.
- Registra intentos en login_attempts para métricas operativas.
- Refresca tokens.
- Progressive backoff for failed attempts.

Autor: Ixchel Beristain
Fecha: 19/11/2025
Updated: 03/01/2026 - Instrumentación de login_attempts
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Mapping, Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.services.user_service import UserService
from app.modules.auth.services.activation_service import ActivationService
from app.modules.auth.services.audit_service import AuditService
from app.modules.auth.services.token_issuer_service import TokenIssuerService
from app.modules.auth.services.session_service import SessionService
from app.modules.auth.repositories.login_attempt_repository import LoginAttemptRepository
from app.modules.auth.enums import LoginFailureReason
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

    Registers sessions in user_sessions table for Auth Metrics.
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
        self.session_service = SessionService(db)
        self.login_attempt_repo = LoginAttemptRepository(db)
        self._rate_limiter = get_rate_limiter()

    # ─────────────────────────────────────────────────────────────────────────
    # Login attempt recording (best-effort, won't block login flow)
    # BD 2.0: Solo se registra si el usuario existe (auth_user_id NOT NULL en DB)
    # ─────────────────────────────────────────────────────────────────────────

    async def _record_login_attempt(
        self,
        *,
        user,  # AppUser o None
        success: bool,
        reason: Optional[LoginFailureReason],
        ip_address: Optional[str],
        user_agent: Optional[str],
    ) -> None:
        """
        Records login attempt to login_attempts table (best-effort).

        BD 2.0: Solo inserta si user existe (auth_user_id es NOT NULL en DB).
        Para intentos con usuario inexistente, NO insertamos - el audit log
        estructurado se mantiene en AuditService.

        If the insert fails, logs the error but doesn't block the login flow.
        """
        # BD 2.0: Si no hay usuario, no podemos insertar (auth_user_id es NOT NULL)
        if user is None:
            logger.debug("login_attempt_skipped: user=None (auth_user_id NOT NULL constraint)")
            return

        try:
            await self.login_attempt_repo.record_attempt(
                user_id=user.user_id,
                auth_user_id=user.auth_user_id,
                success=success,
                reason=reason,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            logger.debug(
                "login_attempt_recorded: user_id=%s auth_user_id=%s success=%s reason=%s",
                user.user_id,
                str(user.auth_user_id)[:8] + "...",
                success,
                reason,
            )
        except Exception as e:
            logger.warning(
                "login_attempts_insert_failed: user_id=%s success=%s error=%s",
                user.user_id,
                success,
                str(e),
            )

    async def _apply_backoff(self, ip_address: str, email: str) -> None:
        """Apply progressive backoff delay based on failed attempt count."""
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
        
        Timing por fases (Bloque B):
            - rate_limit_ms: verificación de rate limiting + backoff
            - db_acquire_ms: tiempo para obtener conexión (pool checkout)
            - db_exec_ms: tiempo de ejecución del SQL
            - password_verify_ms: verificación de contraseña (Argon2)
            - activation_check_ms: verificación de activación
            - token_issue_ms: emisión de JWT
            - session_create_ms: registro de sesión
            - total_ms: tiempo total del login
        """
        start_total = time.perf_counter()
        timings: Dict[str, float] = {}
        email_masked = ""  # Para logs en error (sin datos sensibles)
        
        payload = as_dict(data)
        email = (payload.get("email") or "").strip().lower()
        password = payload.get("password", "")
        ip_address = payload.get("ip_address", "unknown")
        user_agent = payload.get("user_agent")
        
        # Mask email para logs (evita datos sensibles)
        email_masked = email[:3] + "***" if len(email) > 3 else "***"

        if not email or not password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email y contraseña son obligatorios.",
            )

        # ─── Fase: Rate Limiting ───
        rate_start = time.perf_counter()
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
        timings["rate_limit_ms"] = (time.perf_counter() - rate_start) * 1000

        # ─── Fase: DB Query (buscar usuario) con timings detallados ───
        user, db_timings = await self.user_service.get_by_email(email, return_timings=True)
        timings["conn_checkout_ms"] = db_timings.get("conn_checkout_ms", 0)
        timings["db_prep_ms"] = db_timings.get("db_prep_ms", 0)
        timings["db_exec_ms"] = db_timings.get("db_exec_ms", 0)
        
        if not user:
            # ─── Log login_failed con timings disponibles ───
            timings["total_ms"] = (time.perf_counter() - start_total) * 1000
            logger.warning(
                "login_failed reason=user_not_found email=%s "
                "rate_limit_ms=%.2f db_prep_ms=%.2f db_exec_ms=%.2f total_ms=%.2f",
                email_masked,
                timings.get("rate_limit_ms", 0),
                timings.get("db_prep_ms", 0),
                timings.get("db_exec_ms", 0),
                timings["total_ms"],
            )
            
            await self._record_login_attempt(
                user=None,
                success=False,
                reason=LoginFailureReason.user_not_found,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            AuditService.log_login_failed(
                email=email,
                ip_address=ip_address,
                reason="Usuario no encontrado",
                user_agent=user_agent,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales inválidas.",
            )

        # Obtener hash de contraseña desde el modelo actual
        password_hash = getattr(user, "user_password_hash", None)
        if password_hash is None:
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

        # ─── Fase: Password Verify (Argon2) ───
        pw_start = time.perf_counter()
        password_valid = verify_password(password, password_hash)
        timings["password_verify_ms"] = (time.perf_counter() - pw_start) * 1000
        
        if not password_valid:
            # ─── Log login_failed con timings disponibles ───
            timings["total_ms"] = (time.perf_counter() - start_total) * 1000
            logger.warning(
                "login_failed reason=invalid_credentials email=%s "
                "rate_limit_ms=%.2f db_prep_ms=%.2f db_exec_ms=%.2f password_verify_ms=%.2f total_ms=%.2f",
                email_masked,
                timings.get("rate_limit_ms", 0),
                timings.get("db_prep_ms", 0),
                timings.get("db_exec_ms", 0),
                timings.get("password_verify_ms", 0),
                timings["total_ms"],
            )
            
            await self._record_login_attempt(
                user=user,
                success=False,
                reason=LoginFailureReason.invalid_credentials,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            AuditService.log_login_failed(
                email=email,
                ip_address=ip_address,
                reason="Contraseña incorrecta",
                user_agent=user_agent,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales inválidas.",
            )

        # ─── Fase: Activation Check ───
        act_start = time.perf_counter()
        is_active = await self.activation_service.is_active(user)
        timings["activation_check_ms"] = (time.perf_counter() - act_start) * 1000
        
        if not is_active:
            # ─── Log login_failed con timings disponibles ───
            timings["total_ms"] = (time.perf_counter() - start_total) * 1000
            logger.warning(
                "login_failed reason=account_not_activated email=%s "
                "rate_limit_ms=%.2f db_prep_ms=%.2f db_exec_ms=%.2f password_verify_ms=%.2f "
                "activation_check_ms=%.2f total_ms=%.2f",
                email_masked,
                timings.get("rate_limit_ms", 0),
                timings.get("db_prep_ms", 0),
                timings.get("db_exec_ms", 0),
                timings.get("password_verify_ms", 0),
                timings.get("activation_check_ms", 0),
                timings["total_ms"],
            )
            
            await self._record_login_attempt(
                user=user,
                success=False,
                reason=LoginFailureReason.account_not_activated,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            AuditService.log_login_failed(
                email=email,
                ip_address=ip_address,
                reason="Cuenta no activada",
                user_agent=user_agent,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "La cuenta aún no ha sido activada.",
                    "error_code": "ACCOUNT_NOT_ACTIVATED",
                },
            )

        # Login exitoso - reset rate limit counters
        self._reset_rate_limit_counters(ip_address, email)

        # ═══════════════════════════════════════════════════════════════════════
        # SSOT: Garantizar que usuario tiene auth_user_id (fix legacy)
        # ═══════════════════════════════════════════════════════════════════════
        if user.auth_user_id is None:
            from uuid import uuid4

            new_auth_user_id = uuid4()
            user.auth_user_id = new_auth_user_id
            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)
            logger.warning(
                "legacy_user_missing_auth_user_id_fixed user_id=%s new_auth_user_id=%s",
                user.user_id,
                str(new_auth_user_id)[:8] + "...",
            )

        # Record successful login attempt - best effort
        await self._record_login_attempt(
            user=user,
            success=True,
            reason=None,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        AuditService.log_login_success(
            user_id=str(user.user_id),
            email=user.user_email,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # ─── Fase: Token Issue ───
        token_start = time.perf_counter()
        # SSOT: JWT sub = auth_user_id (UUID), NO user_id (INT) - SIEMPRE
        tokens = self.token_issuer.issue_tokens_for_user(user_id=str(user.auth_user_id))
        timings["token_issue_ms"] = (time.perf_counter() - token_start) * 1000

        # ─── Fase: Session Create ───
        session_start = time.perf_counter()
        # Multi-sesión: cada login crea nueva sesión (no revocamos anteriores)
        # BD 2.0: Pasar auth_user_id (UUID SSOT) - NOT NULL en user_sessions
        try:
            session_ok = await self.session_service.create_session(
                user_id=user.user_id,
                auth_user_id=user.auth_user_id,  # BD 2.0 SSOT
                access_token=tokens["access_token"],
                ip_address=ip_address,
                user_agent=user_agent,
            )
            if not session_ok:
                # No bloquea login, pero deja evidencia clara en logs
                logger.error(
                    "session_create_failed: user_id=%s auth_user_id=%s",
                    user.user_id,
                    str(user.auth_user_id)[:8] + "...",
                )
        except Exception:
            # Si SessionService falla con excepción, no queremos 500 por un side-effect
            logger.exception(
                "session_create_exception: user_id=%s auth_user_id=%s",
                user.user_id,
                str(user.auth_user_id)[:8] + "...",
            )
        timings["session_create_ms"] = (time.perf_counter() - session_start) * 1000

        # ─── Log estructurado único con todas las fases ───
        timings["total_ms"] = (time.perf_counter() - start_total) * 1000
        logger.info(
            "login_completed auth_user_id=%s "
            "rate_limit_ms=%.2f conn_checkout_ms=%.2f db_prep_ms=%.2f db_exec_ms=%.2f password_verify_ms=%.2f "
            "activation_check_ms=%.2f token_issue_ms=%.2f session_create_ms=%.2f total_ms=%.2f",
            str(user.auth_user_id)[:8] + "...",
            timings.get("rate_limit_ms", 0),
            timings.get("conn_checkout_ms", 0),
            timings.get("db_prep_ms", 0),
            timings.get("db_exec_ms", 0),
            timings.get("password_verify_ms", 0),
            timings.get("activation_check_ms", 0),
            timings.get("token_issue_ms", 0),
            timings.get("session_create_ms", 0),
            timings["total_ms"],
        )

        return {
            "message": "Login exitoso.",
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": "bearer",
            "user": {
                "user_id": str(user.user_id),
                "auth_user_id": str(user.auth_user_id),
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

        token_payload = verify_token_type(refresh_token, expected_type="refresh")
        if not token_payload:
            logger.warning("Intento de refresh con token inválido o expirado")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido o expirado.",
            )

        user_id_from_token = token_payload.get("sub")
        if not user_id_from_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token sin identificador de usuario.",
            )

        user = await self._get_user_by_token_sub(user_id_from_token)
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

        tokens = self.token_issuer.issue_tokens_for_user(user_id=str(user.auth_user_id))

        AuditService.log_refresh_token_success(
            user_id=str(user.user_id),
        )

        return {
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": "bearer",
        }

    async def _get_user_by_token_sub(self, sub: str):
        """
        Resuelve usuario desde el sub del token.

        SSOT: sub debería ser auth_user_id (UUID).
        Legacy: sub puede ser user_id (INT) durante transición.
        """
        from uuid import UUID

        try:
            auth_user_id = UUID(sub)
            user = await self.user_service.get_by_auth_user_id(auth_user_id)
            if user:
                return user
        except ValueError:
            pass

        try:
            user_id_int = int(sub)
            user = await self.user_service.get_by_id(user_id_int)
            if user:
                logger.warning(
                    "legacy_token_sub_int_used user_id=%s - token debería usar auth_user_id UUID",
                    user_id_int,
                )
                return user
        except ValueError:
            pass

        return None


__all__ = ["LoginFlowService"]

# Fin del script backend/app/modules/auth/services/login_flow_service.py

