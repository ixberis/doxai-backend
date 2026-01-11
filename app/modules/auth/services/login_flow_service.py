# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/login_flow_service.py

Flujo de login y refresh de tokens:
- Aplica rate limiting con RateLimitService (1-roundtrip combined check).
- Valida credenciales.
- Verifica activación de cuenta.
- Emite tokens de acceso/refresh.
- Registra sesión en user_sessions para métricas.
- Registra intentos en login_attempts para métricas operativas.
- Refresca tokens.
- Progressive backoff for failed attempts.

Autor: Ixchel Beristain
Fecha: 19/11/2025
Updated: 11/01/2026 - LoginTelemetry + combined rate limiting (1 roundtrip)
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
from app.modules.auth.services.login_telemetry import LoginTelemetry
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
    
    NEW: Uses combined rate limit check (1 roundtrip) and LoginTelemetry
    for unified structured logging.

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

    async def _apply_backoff_if_needed(
        self, email: str, current_count: int, is_failure: bool, telemetry: LoginTelemetry
    ) -> float:
        """
        Apply progressive backoff delay ONLY for repeated failures.
        
        Returns:
            Actual delay applied in seconds (0 if no delay).
            
        Rules:
        - Success: NEVER sleep (backoff=0)
        - Failure with current_count < 2: No sleep yet
        - Failure with current_count >= 2: Progressive backoff
        """
        if not is_failure:
            telemetry.mark_timing("backoff_ms", 0)
            return 0.0
        
        if current_count < 2:
            telemetry.mark_timing("backoff_ms", 0)
            return 0.0
        
        delay = _get_backoff_delay(current_count)
        if delay > 0:
            logger.debug(
                "backoff_applied email=%s attempts=%d delay_sec=%.2f",
                telemetry.email_masked, current_count, delay
            )
            await asyncio.sleep(delay)
        
        telemetry.mark_timing("backoff_ms", delay * 1000)
        return delay

    async def login(
        self, data: Mapping[str, Any] | Any, *, request: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Autentica al usuario y retorna tokens.

        data esperado:
            - email
            - password
            - recaptcha_token (ya validado antes por AuthService)
            - ip_address
            - user_agent
        
        Uses LoginTelemetry for unified structured logging.
        Uses combined rate limit check (1 roundtrip instead of 2).
        """
        payload = as_dict(data)
        email = (payload.get("email") or "").strip().lower()
        password = payload.get("password", "")
        ip_address = payload.get("ip_address", "unknown")
        user_agent = payload.get("user_agent")
        
        # Use request from parameter (preferred) or fallback to payload (legacy)
        # Pop _request from payload to prevent serialization/logging leaks
        _request = request or payload.pop("_request", None)
        
        # Initialize telemetry (email masked internally)
        telemetry = LoginTelemetry.create(email)

        if not email or not password:
            telemetry.finalize(_request, result="missing_credentials")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email y contraseña son obligatorios.",
            )

        # ─── Fase: Combined Rate Limiting (1 roundtrip) ───
        with telemetry.measure("rate_limit_check_ms"):
            rl_decision = await self._rate_limiter.check_login_limits_combined(
                email=email,
                ip_address=ip_address,
            )
        
        # Copy REAL rate limit timings to telemetry (no invented breakdown)
        telemetry.mark_timing("rate_limit_total_ms", rl_decision.timings.get("total_ms", 0))
        telemetry.mark_timing("redis_rtt_ms", rl_decision.timings.get("redis_rtt_ms", 0))
        telemetry.set_flag("rate_limit_roundtrips", rl_decision.roundtrips)
        
        if not rl_decision.allowed:
            AuditService.log_login_blocked(email=email, ip_address=ip_address)
            # CRITICAL: finalize() BEFORE raising to ensure request.state is populated
            telemetry.finalize(_request, result="rate_limited")
            
            detail = "Demasiados intentos de inicio de sesión. Intente más tarde."
            if rl_decision.blocked_by == "ip":
                detail = "Demasiados intentos desde esta dirección IP. Intente más tarde."
            
            raise RateLimitExceeded(
                retry_after=rl_decision.retry_after,
                detail=detail,
            )

        # ─── Fase: DB Query (buscar usuario) - CORE MODE ───
        with telemetry.measure("lookup_user_ms"):
            user = await self.user_service.get_by_email_core_login(email)
        
        telemetry.set_flag("found", user is not None)
        
        if not user:
            # Backoff for failures
            await self._apply_backoff_if_needed(
                email, rl_decision.email_count, is_failure=True, telemetry=telemetry
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
            
            telemetry.finalize(_request, result="user_not_found")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales inválidas.",
            )

        # Obtener hash de contraseña desde el DTO (LoginUserDTO)
        password_hash = getattr(user, "user_password_hash", None)

        if password_hash is None:
            logger.error(
                "LOGIN: usuario %s no tiene hash de contraseña.",
                getattr(user, "user_id", None),
            )
            AuditService.log_login_failed(
                email=email,
                ip_address=ip_address,
                reason="Configuración de usuario inválida (sin hash de contraseña)",
                user_agent=user_agent,
            )
            telemetry.finalize(_request, result="internal_error")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Configuración de usuario inválida.",
            )

        # ─── Fase: Password Verify (Argon2id) ───
        with telemetry.measure("argon2_verify_ms"):
            password_valid = verify_password(password, password_hash)
        
        if not password_valid:
            # Backoff for failures
            await self._apply_backoff_if_needed(
                email, rl_decision.email_count, is_failure=True, telemetry=telemetry
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
            
            telemetry.finalize(_request, result="invalid_credentials")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales inválidas.",
            )

        # ─── Fase: Activation Check ───
        with telemetry.measure("activation_check_ms"):
            is_active = user.user_is_activated and not user.is_deleted
        
        if not is_active:
            # Backoff for failures
            await self._apply_backoff_if_needed(
                email, rl_decision.email_count, is_failure=True, telemetry=telemetry
            )
            
            AuditService.log_login_failed(
                email=email,
                ip_address=ip_address,
                reason="Cuenta no activada" if not user.user_is_activated else "Cuenta eliminada",
                user_agent=user_agent,
            )
            
            result_type = "account_not_activated" if not user.user_is_activated else "account_deleted"
            telemetry.finalize(_request, result=result_type)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "La cuenta aún no ha sido activada.",
                    "error_code": "ACCOUNT_NOT_ACTIVATED",
                },
            )

        # Login exitoso - reset rate limit counters (async, 1 roundtrip)
        with telemetry.measure("rate_limit_reset_ms"):
            reset_timings = await self._rate_limiter.reset_login_limits_async(
                email=email,
                ip_address=ip_address,
            )
        telemetry.set_flag("rate_limit_reset_roundtrips", reset_timings.get("roundtrips", 0))

        # ═══════════════════════════════════════════════════════════════════════
        # SSOT: auth_user_id validation (DTO ya tiene este campo)
        # Si es None (legacy), generamos UUID y lo persistimos via repo
        # ═══════════════════════════════════════════════════════════════════════
        auth_user_id = user.auth_user_id
        auth_user_id_present_initially = auth_user_id is not None
        used_legacy_ssot_fix = False
        
        telemetry.set_flag("auth_user_id_present", auth_user_id_present_initially)
        
        if auth_user_id is None:
            # Caso legacy extremadamente raro - usuario sin UUID
            from uuid import uuid4
            from app.modules.auth.repositories import UserRepository
            
            with telemetry.measure("legacy_ssot_fix_ms"):
                new_auth_user_id = uuid4()
                repo = UserRepository(self.db)
                
                try:
                    updated = await repo.set_auth_user_id_if_missing(user.user_id, new_auth_user_id)
                    if updated:
                        await self.db.commit()
                        auth_user_id = new_auth_user_id
                        used_legacy_ssot_fix = True
                        logger.warning(
                            "legacy_user_missing_auth_user_id_fixed user_id=%s new_auth_user_id=%s",
                            user.user_id,
                            str(new_auth_user_id)[:8] + "...",
                        )
                    else:
                        auth_user_id = new_auth_user_id
                        used_legacy_ssot_fix = True
                        logger.info(
                            "legacy_user_auth_user_id_race_condition user_id=%s using_local_uuid=%s",
                            user.user_id,
                            str(new_auth_user_id)[:8] + "...",
                        )
                except Exception as e:
                    auth_user_id = new_auth_user_id
                    used_legacy_ssot_fix = True
                    logger.warning(
                        "legacy_user_auth_user_id_update_failed user_id=%s error=%s using_local_uuid=%s",
                        user.user_id,
                        str(e),
                        str(new_auth_user_id)[:8] + "...",
                    )
            
            telemetry.set_flag("used_legacy_ssot_fix", True)
        else:
            telemetry.set_flag("used_legacy_ssot_fix", False)

        # Record successful login - AuditService (best effort)
        AuditService.log_login_success(
            user_id=str(user.user_id),
            email=user.user_email,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # ─── Fase: Token Issue ───
        with telemetry.measure("issue_token_ms"):
            # SSOT: JWT sub = auth_user_id (UUID), NO user_id (INT) - SIEMPRE
            tokens = self.token_issuer.issue_tokens_for_user(user_id=str(auth_user_id))

        # ─── Fase: Session Create ───
        with telemetry.measure("session_create_ms"):
            try:
                session_ok = await self.session_service.create_session(
                    user_id=user.user_id,
                    auth_user_id=auth_user_id,
                    access_token=tokens["access_token"],
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                if not session_ok:
                    logger.error(
                        "session_create_failed: user_id=%s auth_user_id=%s",
                        user.user_id,
                        str(auth_user_id)[:8] + "...",
                    )
            except Exception:
                logger.exception(
                    "session_create_exception: user_id=%s auth_user_id=%s",
                    user.user_id,
                    str(auth_user_id)[:8] + "...",
                )

        # ─── Finalize telemetry (single structured log) ───
        telemetry.finalize(_request, result="success")

        return {
            "message": "Login exitoso.",
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": "bearer",
            "user": {
                "user_id": str(user.user_id),
                "auth_user_id": str(auth_user_id),
                "user_email": user.user_email,
                "user_full_name": user.user_full_name,
                "user_role": user.user_role,
                "user_status": user.user_status,
            },
        }

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
