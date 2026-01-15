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
Updated: 12/01/2026 - Timing oracle protection via dummy verify
"""

from __future__ import annotations

import asyncio
import logging
import os
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
from app.shared.security.auth_context_cache import get_auth_context_cache

logger = logging.getLogger(__name__)


# Progressive backoff delays (seconds) based on attempt count
BACKOFF_DELAYS = [0, 0.2, 0.4, 0.8, 1.2, 2.0]  # Max 2 seconds

# ─────────────────────────────────────────────────────────────────────────────
# Timing oracle protection: dummy Argon2 hash for user_not_found path
# ─────────────────────────────────────────────────────────────────────────────
# When a user is not found, we run verify_password against this dummy hash
# to make the response time indistinguishable from a wrong password.
# This prevents email enumeration via timing attacks.
#
# Config: LOGIN_DUMMY_VERIFY_ON_USER_NOT_FOUND
#   - "true" (default): always run dummy verify (recommended for prod)
#   - "false": skip dummy verify (faster dev/test, NOT for prod)
# ─────────────────────────────────────────────────────────────────────────────
LOGIN_DUMMY_VERIFY_ENABLED = os.getenv(
    "LOGIN_DUMMY_VERIFY_ON_USER_NOT_FOUND", "true"
).lower() in ("1", "true", "yes")

# ─────────────────────────────────────────────────────────────────────────────
# Legacy refresh token sub (INT) support flag
# ─────────────────────────────────────────────────────────────────────────────
# During BD 2.0 migration, some old refresh tokens may contain INT user_id
# instead of UUID auth_user_id. This flag controls whether to support them.
#
# Config: AUTH_ALLOW_LEGACY_REFRESH_SUB
#   - "false" (default): reject legacy INT subs with 401
#   - "true": fallback to ORM path (for migration period only)
# ─────────────────────────────────────────────────────────────────────────────
AUTH_ALLOW_LEGACY_REFRESH_SUB = os.getenv(
    "AUTH_ALLOW_LEGACY_REFRESH_SUB", "false"
).lower() in ("1", "true", "yes")

# Pre-computed Argon2id hash for dummy verification (hash of random string)
# This hash was generated with: hash_password("__dummy_password_do_not_use__")
DUMMY_ARGON2_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$"
    "c2FsdF9mb3JfZHVtbXlfaGFzaA$"
    "dGhpc19pc19hX2R1bW15X2hhc2hfZm9yX3RpbWluZ19vcmFjbGVfcHJvdGVjdGlvbg"
)


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
    # BD 2.0 P0: Registra TODOS los intentos incluyendo user_not_found
    # ─────────────────────────────────────────────────────────────────────────

    async def _record_login_attempt(
        self,
        *,
        user,  # AppUser, LoginUserDTO, LoginUserCacheData, or None
        success: bool,
        reason: Optional[LoginFailureReason],
        ip_address: Optional[str],
        user_agent: Optional[str],
        email: Optional[str] = None,  # Required for user_not_found traceability
    ) -> None:
        """
        Records login attempt to login_attempts table (best-effort).

        BD 2.0 P0: Registra TODOS los intentos incluyendo user_not_found.
        - Si user existe: usa user_id y auth_user_id
        - Si user es None: inserta con user_id=NULL, auth_user_id=NULL, email_hash

        If the insert fails, logs the error but doesn't block the login flow.
        """
        try:
            # Extract user fields if user exists
            user_id = getattr(user, "user_id", None) if user else None
            auth_user_id = getattr(user, "auth_user_id", None) if user else None
            
            await self.login_attempt_repo.record_attempt(
                user_id=user_id,
                auth_user_id=auth_user_id,
                success=success,
                reason=reason,
                ip_address=ip_address,
                user_agent=user_agent,
                email=email,  # Se hashea en el repositorio
            )
            
            # Log with appropriate detail level
            if user:
                logger.debug(
                    "login_attempt_recorded: user_id=%s auth_user_id=%s success=%s reason=%s",
                    user_id,
                    str(auth_user_id)[:8] + "..." if auth_user_id else "None",
                    success,
                    reason,
                )
            else:
                logger.debug(
                    "login_attempt_recorded: user_not_found success=%s reason=%s ip=%s",
                    success,
                    reason,
                    ip_address,
                )
        except Exception as e:
            logger.warning(
                "login_attempts_insert_failed: user_id=%s success=%s error=%s",
                getattr(user, "user_id", None) if user else None,
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
            
            # P0 FIX: Registrar intento en login_attempts ANTES del 429
            # Esto permite que "Rate limits activados" se contabilice en dashboard
            await self._record_login_attempt(
                user=None,  # No resolvemos usuario para rate limit (no penalizar lookup)
                success=False,
                reason=LoginFailureReason.rate_limited,
                ip_address=ip_address,
                user_agent=user_agent,
                email=email,  # Se hashea en el repositorio
            )
            
            # CRITICAL: finalize() BEFORE raising to ensure request.state is populated
            telemetry.finalize(_request, result="rate_limited")
            
            detail = "Demasiados intentos de inicio de sesión. Intente más tarde."
            if rl_decision.blocked_by == "ip":
                detail = "Demasiados intentos desde esta dirección IP. Intente más tarde."
            
            raise RateLimitExceeded(
                retry_after=rl_decision.retry_after,
                detail=detail,
            )

        # ─── Fase: User Lookup (con cache) ───
        # Estrategia: Cache contiene user_id + status flags (NO password_hash, email, name)
        # Cache HIT → PK lookup para password_hash → Argon2 verify
        # Cache MISS → Full email lookup → SET cache
        # NOTA: Solo 1 Argon2 verify por request (el normal)
        
        from app.shared.security.login_user_cache import (
            get_login_user_cache,
            LoginUserCacheData,
        )
        from app.shared.security.login_cache_metrics import (
            record_cache_hit,
            record_cache_miss,
            record_cache_error,
            record_early_reject,
            observe_cache_get_latency,
            observe_cache_set_latency,
            observe_password_hash_lookup_latency,
        )
        from app.modules.auth.repositories import UserRepository
        
        user = None
        password_hash: Optional[str] = None
        cache_hit = False
        early_reject_reason: Optional[str] = None
        
        login_cache = get_login_user_cache()
        
        # Cache GET
        with telemetry.measure("login_user_cache_get_ms"):
            cached_data, cache_result = await login_cache.get_cached(email)
        
        # Record Prometheus metrics for cache GET
        observe_cache_get_latency(cache_result.duration_ms / 1000)  # ms to seconds
        
        telemetry.set_flag("login_user_cache_hit", cache_result.cache_hit)
        if cache_result.fallback_reason:
            telemetry.set_flag("cache_fallback_reason", cache_result.fallback_reason)
        
        # Record cache hit/miss/error metrics (SINGLE POINT - no double counting)
        # Canonical semantics:
        # - hit_total: cache returned valid data
        # - miss_total: ONLY when fallback_reason="cache_miss" (key genuinely not found)
        # - error_total: cache operation failed (redis_error, redis_unavailable, etc.)
        # 
        # Error cases do NOT increment miss_total to keep metrics semantically clean:
        # miss_total should reflect "key not in cache", not "cache unavailable"
        if cache_result.cache_hit:
            record_cache_hit()
        elif cache_result.error:
            # Error path: only record error, NOT miss
            error_type = cache_result.fallback_reason or "redis_error"
            record_cache_error(error_type)  # Will normalize to VALID_ERROR_TYPES
        elif cache_result.fallback_reason == "cache_miss":
            # Clean miss path: key not found, no errors
            # CANONICAL: only increment miss_total when fallback_reason is exactly "cache_miss"
            record_cache_miss()
        # Note: cache_disabled case (fallback_reason="cache_disabled") does not increment
        # miss_total - it's not a cache miss, the cache was intentionally disabled
        
        if cache_result.cache_hit and cached_data:
            cache_hit = True
            
            # Check early reject condition - lo procesamos DESPUÉS del Argon2 verify
            if not cached_data.can_proceed_to_password_check:
                if cached_data.is_deleted:
                    early_reject_reason = "account_deleted"
                    record_early_reject("deleted")
                else:
                    early_reject_reason = "account_not_activated"
                    record_early_reject("not_activated")
                telemetry.set_flag("early_reject", True)
            
            # Cache HIT path: PK lookup para password_hash solamente
            with telemetry.measure("password_hash_lookup_ms"):
                repo = UserRepository(self.db)
                password_hash = await repo.get_password_hash_by_id(cached_data.user_id)
            
            # Record password hash lookup latency
            pk_lookup_ms = telemetry.timings.get("password_hash_lookup_ms", 0)
            observe_password_hash_lookup_latency(pk_lookup_ms / 1000)  # ms to seconds
            
            # lookup_user_ms = 0 en cache HIT (no email lookup)
            telemetry.mark_timing("lookup_user_ms", 0.0)
            
            if password_hash:
                # Construir objeto user-like para compatibilidad con el resto del flujo
                user = cached_data  # LoginUserCacheData tiene los campos necesarios
            else:
                # User deleted o no existe - invalidar cache y fallar
                await login_cache.invalidate(email)
                user = None
                cache_hit = False  # Force full lookup
        
        # Cache MISS path: Full email lookup
        if not cache_hit or user is None:
            with telemetry.measure("lookup_user_ms"):
                user = await self.user_service.get_by_email_core_login(email)
            
            # password_hash_lookup_ms = 0 en cache MISS (full lookup incluye hash)
            telemetry.mark_timing("password_hash_lookup_ms", 0.0)
            
            if user:
                password_hash = getattr(user, "user_password_hash", None)
                
                # SET cache (best-effort, async-safe) - PAYLOAD MÍNIMO + user_role (no PII)
                with telemetry.measure("login_user_cache_set_ms"):
                    cache_data = LoginUserCacheData(
                        user_id=user.user_id,
                        auth_user_id=user.auth_user_id,
                        user_status=user.user_status,
                        user_is_activated=user.user_is_activated,
                        user_role=getattr(user, "user_role", None) or "user",
                        deleted_at=user.deleted_at,
                    )
                    set_result = await login_cache.set_cached(email, cache_data)
                
                # Record cache SET latency
                observe_cache_set_latency(set_result.duration_ms / 1000)  # ms to seconds
                
                # Record SET error if any (normalized label)
                if set_result.error:
                    record_cache_error("set_error")  # Normalized by record_cache_error
        
        telemetry.set_flag("found", user is not None)
        
        if not user:
            # ─── Timing Oracle Protection ───
            # Run dummy Argon2 verify to make timing indistinguishable from wrong password
            if LOGIN_DUMMY_VERIFY_ENABLED:
                with telemetry.measure("argon2_verify_ms"):
                    verify_password(password, DUMMY_ARGON2_HASH)
                telemetry.set_flag("dummy_verify", True)
            else:
                telemetry.mark_timing("argon2_verify_ms", 0.0)
                telemetry.set_flag("dummy_verify", False)
            
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
                email=email,  # Para trazabilidad (se hashea)
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

        # password_hash ya está asignado desde cache HIT o cache MISS path
        # NO hacer re-fetch aquí

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
        # CRITICAL: Always run Argon2 verify even if we know user will be rejected
        # This prevents timing oracle attacks
        with telemetry.measure("argon2_verify_ms"):
            password_valid = verify_password(password, password_hash)
        
        # ─── Check early reject AFTER Argon2 (timing consistent) ───
        # ZERO ENUMERATION: Return same 401 for ALL failure cases
        # Internal logging preserves the actual reason for debugging
        if early_reject_reason:
            await self._apply_backoff_if_needed(
                email, rl_decision.email_count, is_failure=True, telemetry=telemetry
            )
            
            # Log actual reason internally (for debugging/audit)
            if early_reject_reason == "account_deleted":
                reason_text = "Cuenta eliminada"
                result_type = "account_deleted"
                failure_reason = LoginFailureReason.inactive_user
            else:
                reason_text = "Cuenta no activada"
                result_type = "account_not_activated"
                failure_reason = LoginFailureReason.account_not_activated
            
            # P0: Record failed attempt in DB for Auth Operativo metrics
            await self._record_login_attempt(
                user=user,
                success=False,
                reason=failure_reason,
                ip_address=ip_address,
                user_agent=user_agent,
                email=email,
            )
            
            AuditService.log_login_failed(
                email=email,
                ip_address=ip_address,
                reason=reason_text,
                user_agent=user_agent,
            )
            
            telemetry.finalize(_request, result=result_type)
            # ZERO ENUMERATION: Same 401 + same message as wrong password
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales inválidas.",
            )
        
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
                email=email,
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

        # ─── Fase: Activation Check (for cache MISS path) ───
        # ZERO ENUMERATION: Return same 401 for inactive accounts
        with telemetry.measure("activation_check_ms"):
            is_active = user.user_is_activated and not getattr(user, "is_deleted", False)
        
        if not is_active:
            # Backoff for failures
            await self._apply_backoff_if_needed(
                email, rl_decision.email_count, is_failure=True, telemetry=telemetry
            )
            
            # Log actual reason internally
            if not user.user_is_activated:
                reason_text = "Cuenta no activada"
                result_type = "account_not_activated"
                failure_reason = LoginFailureReason.account_not_activated
            else:
                reason_text = "Cuenta eliminada"
                result_type = "account_deleted"
                failure_reason = LoginFailureReason.inactive_user
            
            # P0: Record failed attempt in DB for Auth Operativo metrics
            await self._record_login_attempt(
                user=user,
                success=False,
                reason=failure_reason,
                ip_address=ip_address,
                user_agent=user_agent,
                email=email,
            )
            
            AuditService.log_login_failed(
                email=email,
                ip_address=ip_address,
                reason=reason_text,
                user_agent=user_agent,
            )
            
            telemetry.finalize(_request, result=result_type)
            # ZERO ENUMERATION: Same 401 + same message
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales inválidas.",
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

        # ─────────────────────────────────────────────────────────────────────────
        # CACHE HIT FIX: user puede ser LoginUserCacheData (sin PII) o LoginUserDTO
        # Para audit y response, usamos email del payload y user_role del cache/DTO
        # 
        # SEGURIDAD:
        # - email: SIEMPRE del payload (no se cachea por privacidad)
        # - user_role: del cache o DTO (incluido en cache desde v2, no es PII)
        # - user_full_name: fallback a "" (NO se cachea, PII)
        # ─────────────────────────────────────────────────────────────────────────
        
        # Email: usar del payload (ya disponible, NO del cache por seguridad)
        user_email_for_response = email  # Del payload, normalizado
        
        # user_role: priorizar del user (cache o DTO), con fallback seguro
        # En cache HIT v2+, user_role está disponible. En cache antiguo, fallback a "user"
        user_role_for_response = getattr(user, "user_role", None) or "user"
        
        # user_full_name: NO está en cache (PII), fallback a ""
        # Si necesitas el nombre real, se podría hacer mini-lookup pero no es crítico
        user_full_name_for_response = getattr(user, "user_full_name", None) or ""

        # ─── Record successful login attempt in DB ───
        # P0: Persistir en login_attempts para métricas Auth Operativo
        await self._record_login_attempt(
            user=user,
            success=True,
            reason=None,  # No reason for success
            ip_address=ip_address,
            user_agent=user_agent,
            email=email,
        )

        # Record successful login - AuditService (best effort, structured logs)
        # Usar email del payload, NO de user (que puede ser LoginUserCacheData)
        AuditService.log_login_success(
            user_id=str(user.user_id),
            email=user_email_for_response,  # Del payload, no del cache
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
                "user_email": user_email_for_response,
                "user_full_name": user_full_name_for_response,
                "user_role": user_role_for_response,
                "user_status": user.user_status,
            },
        }

    async def refresh_tokens(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        """
        Refresca tokens de acceso a partir de un refresh_token válido.
        
        OPTIMIZADO (2026-01-15):
        - Usa cache Redis + Core SQL en lugar de ORM
        - AuthContextDTO.is_active elimina query extra de ActivationService
        - Instrumentación completa de fases para diagnóstico
        
        data esperado:
            - refresh_token
        """
        import time
        from uuid import UUID
        
        t_start = time.perf_counter()
        timings: Dict[str, float] = {
            "jwt_decode_ms": 0.0,
            "cache_lookup_ms": 0.0,
            "db_lookup_ms": 0.0,
            "db_execute_ms": 0.0,
            "activation_check_ms": 0.0,
            "issue_token_ms": 0.0,
            "audit_ms": 0.0,
            "total_ms": 0.0,
        }
        auth_user_id_masked = "unknown"
        cache_hit = False
        cache_reason = "n/a"
        
        payload = as_dict(data)
        refresh_token = payload.get("refresh_token")

        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Refresh token requerido.",
            )

        # ─── Fase: JWT Decode ───
        t_jwt_start = time.perf_counter()
        token_payload = verify_token_type(refresh_token, expected_type="refresh")
        timings["jwt_decode_ms"] = (time.perf_counter() - t_jwt_start) * 1000
        
        if not token_payload:
            logger.warning("refresh_token_invalid jwt_decode_failed")
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

        # ─── Parse UUID ───
        try:
            auth_user_id = UUID(user_id_from_token)
            auth_user_id_masked = str(auth_user_id)[:8] + "..."
        except ValueError:
            # Legacy INT sub - controlled via AUTH_ALLOW_LEGACY_REFRESH_SUB
            if AUTH_ALLOW_LEGACY_REFRESH_SUB:
                logger.warning(
                    "refresh_token_legacy_path_used sub=%s legacy_enabled=true",
                    user_id_from_token,
                )
                return await self._refresh_tokens_legacy(data, timings, t_start)
            else:
                logger.warning(
                    "refresh_token_legacy_rejected sub=%s legacy_enabled=false",
                    user_id_from_token,
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token format no soportado. Por favor, inicie sesión nuevamente.",
                )

        # ─── Fase: Try Redis Cache First ───
        auth_context = None
        t_cache_start = time.perf_counter()
        
        try:
            cache = get_auth_context_cache()
            cached_mapping, cache_result = await cache.get_cached(auth_user_id)
            timings["cache_lookup_ms"] = (time.perf_counter() - t_cache_start) * 1000
            
            if cached_mapping:
                from app.modules.auth.schemas.auth_context_dto import AuthContextDTO
                auth_context = AuthContextDTO.from_mapping(cached_mapping)
                cache_hit = True
                cache_reason = "hit"
            elif cache_result.error:
                cache_reason = cache_result.error  # disabled|redis_not_available|deserialize_failed|key_not_found
            else:
                cache_reason = "key_not_found"
        except Exception as e:
            timings["cache_lookup_ms"] = (time.perf_counter() - t_cache_start) * 1000
            cache_reason = "get_failed"
            logger.debug("refresh_token_cache_error: %s", str(e))

        # ─── Fase: Core DB Lookup (if cache miss) ───
        if auth_context is None:
            t_db_start = time.perf_counter()
            try:
                auth_context, db_timings = await self.user_service.get_by_auth_user_id_core_ctx(auth_user_id)
                timings["db_lookup_ms"] = (time.perf_counter() - t_db_start) * 1000
                timings["db_execute_ms"] = db_timings.get("execute_ms", 0)
                
                # Cache the result for future requests (best-effort)
                if auth_context:
                    try:
                        cache = get_auth_context_cache()
                        await cache.set_cached(auth_user_id, auth_context)
                    except Exception:
                        pass
            except Exception as e:
                timings["db_lookup_ms"] = (time.perf_counter() - t_db_start) * 1000
                logger.exception("refresh_token_db_lookup_failed auth_user_id=%s", auth_user_id_masked)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Error interno al validar usuario.",
                )

        if not auth_context:
            self._log_refresh_timings(timings, t_start, auth_user_id_masked, cache_hit, cache_reason, "user_not_found")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario no encontrado.",
            )
        
        # ─── Validar estado activo (NO query extra - usa DTO.is_active property) ───
        t_active_start = time.perf_counter()
        is_active = auth_context.is_active  # Property check, no query
        timings["activation_check_ms"] = (time.perf_counter() - t_active_start) * 1000
        
        if not is_active:
            self._log_refresh_timings(timings, t_start, auth_user_id_masked, cache_hit, cache_reason, "inactive_user")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario inactivo o no activado.",
            )

        # ─── Fase: Issue new tokens ───
        t_issue_start = time.perf_counter()
        tokens = self.token_issuer.issue_tokens_for_user(user_id=str(auth_user_id))
        timings["issue_token_ms"] = (time.perf_counter() - t_issue_start) * 1000

        # ─── Audit (sync, no await needed) ───
        t_audit_start = time.perf_counter()
        AuditService.log_refresh_token_success(
            user_id=str(auth_context.user_id),
        )
        timings["audit_ms"] = (time.perf_counter() - t_audit_start) * 1000

        self._log_refresh_timings(timings, t_start, auth_user_id_masked, cache_hit, cache_reason, "success")

        return {
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": "bearer",
        }

    def _log_refresh_timings(
        self,
        timings: Dict[str, float],
        t_start: float,
        auth_user_id_masked: str,
        cache_hit: bool,
        cache_reason: str,
        result: str,
    ) -> None:
        """
        Log estructurado de timings de refresh token.
        
        Campos:
        - auth_user_id: truncado (8 chars + ...)
        - result: success|fail|user_not_found|inactive_user
        - cache_hit: true/false
        - cache_reason: hit|key_not_found|disabled|redis_not_available|deserialize_failed|get_failed
        - jwt_decode_ms, cache_lookup_ms, db_lookup_ms, db_execute_ms
        - activation_check_ms, issue_token_ms, audit_ms, total_ms
        """
        import time
        timings["total_ms"] = (time.perf_counter() - t_start) * 1000
        
        # Determinar log level basado en latencia o resultado
        is_slow = timings["total_ms"] >= 500
        is_error = result not in ("success",)
        log_level = logging.INFO if (is_slow or is_error) else logging.DEBUG
        
        if logger.isEnabledFor(log_level):
            logger.log(
                log_level,
                "refresh_token_breakdown auth_user_id=%s result=%s cache_hit=%s cache_reason=%s "
                "jwt_decode_ms=%.1f cache_lookup_ms=%.1f db_lookup_ms=%.1f db_execute_ms=%.1f "
                "activation_check_ms=%.1f issue_token_ms=%.1f audit_ms=%.1f total_ms=%.1f",
                auth_user_id_masked,
                result,
                cache_hit,
                cache_reason,
                timings.get("jwt_decode_ms", 0),
                timings.get("cache_lookup_ms", 0),
                timings.get("db_lookup_ms", 0),
                timings.get("db_execute_ms", 0),
                timings.get("activation_check_ms", 0),
                timings.get("issue_token_ms", 0),
                timings.get("audit_ms", 0),
                timings["total_ms"],
            )

    async def _refresh_tokens_legacy(
        self, data: Mapping[str, Any] | Any, timings: Dict[str, float], t_start: float
    ) -> Dict[str, Any]:
        """
        Fallback para tokens con sub INT (legacy).
        Usa ORM path para compatibilidad.
        """
        import time
        
        payload = as_dict(data)
        refresh_token = payload.get("refresh_token")
        token_payload = verify_token_type(refresh_token, expected_type="refresh")
        user_id_from_token = token_payload.get("sub")
        
        t_db_start = time.perf_counter()
        user = await self._get_user_by_token_sub(user_id_from_token)
        timings["db_lookup_ms"] = (time.perf_counter() - t_db_start) * 1000
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario no encontrado.",
            )
        
        t_active_start = time.perf_counter()
        is_active = await self.activation_service.is_active(user)
        timings["is_active_check_ms"] = (time.perf_counter() - t_active_start) * 1000
        
        if not is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario inactivo o no activado.",
            )

        t_issue_start = time.perf_counter()
        tokens = self.token_issuer.issue_tokens_for_user(user_id=str(user.auth_user_id))
        timings["issue_token_ms"] = (time.perf_counter() - t_issue_start) * 1000

        AuditService.log_refresh_token_success(user_id=str(user.user_id))
        
        timings["total_ms"] = (time.perf_counter() - t_start) * 1000
        logger.warning(
            "refresh_token_legacy_path user_id=%s total_ms=%.1f db_ms=%.1f",
            user.user_id,
            timings["total_ms"],
            timings["db_lookup_ms"],
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
