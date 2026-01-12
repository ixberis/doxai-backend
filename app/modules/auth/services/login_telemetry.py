# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/login_telemetry.py

LoginTelemetry: Unified timing and flag tracking for login flow.

Features:
- Single structured log event (login_timing_breakdown)
- Threshold-based INFO/DEBUG gating
- Consistent request.state population in all paths (success/error)
- Privacy-safe: email masked, no password_valid in logs

Autor: Ixchel Beristain
Fecha: 11/01/2026
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional

logger = logging.getLogger(__name__)

# Configurable via env: default 1200ms
SLOW_LOGIN_THRESHOLD_MS = float(os.environ.get("SLOW_LOGIN_THRESHOLD_MS", "1200"))

# Debug flag to force INFO logging for all logins (useful for temporary debugging)
LOGIN_TELEMETRY_DEBUG = os.environ.get("LOGIN_TELEMETRY_DEBUG", "0").lower() in ("1", "true", "yes")

# Result types for structured logging
LoginResult = Literal[
    "success",
    "user_not_found",
    "invalid_credentials",
    "account_not_activated",
    "account_deleted",
    "rate_limited",
    "missing_credentials",
    "internal_error",
]


@dataclass
class LoginTelemetry:
    """
    Unified telemetry collector for login flow.
    
    Usage:
        telemetry = LoginTelemetry(email="user@example.com")
        
        # Mark timings
        with telemetry.measure("lookup_user_ms"):
            user = await lookup_user(email)
        
        # Or manually
        t0 = time.perf_counter()
        do_something()
        telemetry.mark_timing("something_ms", (time.perf_counter() - t0) * 1000)
        
        # Set flags
        telemetry.set_flag("auth_user_id_present", True)
        
        # Finalize (logs + request.state)
        telemetry.finalize(request, result="success")
    """
    
    email_masked: str = ""
    start_time: float = field(default_factory=time.perf_counter)
    timings: Dict[str, float] = field(default_factory=dict)
    flags: Dict[str, Any] = field(default_factory=dict)
    _finalized: bool = field(default=False, repr=False)
    
    def __post_init__(self):
        """Initialize with mode flag."""
        self.flags["mode"] = "core_login"
    
    @classmethod
    def create(cls, email: str) -> "LoginTelemetry":
        """Factory method with email masking."""
        masked = email[:3] + "***" if len(email) > 3 else "***"
        return cls(email_masked=masked)
    
    def mark_timing(self, name: str, value_ms: float) -> None:
        """Record a timing value in milliseconds."""
        self.timings[name] = value_ms
    
    def set_flag(self, name: str, value: Any) -> None:
        """Set a diagnostic flag."""
        self.flags[name] = value
    
    class TimingContext:
        """Context manager for measuring a timing."""
        
        def __init__(self, telemetry: "LoginTelemetry", name: str):
            self.telemetry = telemetry
            self.name = name
            self.start: float = 0
        
        def __enter__(self) -> "LoginTelemetry.TimingContext":
            self.start = time.perf_counter()
            return self
        
        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            elapsed_ms = (time.perf_counter() - self.start) * 1000
            self.telemetry.mark_timing(self.name, elapsed_ms)
            return None  # Don't suppress exceptions
    
    def measure(self, name: str) -> TimingContext:
        """Create a context manager for timing a block."""
        return self.TimingContext(self, name)
    
    def finalize(
        self,
        request: Optional[Any],
        result: LoginResult,
    ) -> Dict[str, Any]:
        """
        Finalize telemetry: calculate total, set request.state, emit log.
        
        MUST be called in all exit paths (success, error, exception).
        
        Args:
            request: FastAPI Request object (can be None)
            result: Login result for logging
            
        Returns:
            Dict with all timings and flags for optional response inclusion
        """
        if self._finalized:
            logger.warning("LoginTelemetry.finalize() called multiple times")
            return self._build_summary()
        
        self._finalized = True
        
        # Calculate total
        self.timings["total_ms"] = (time.perf_counter() - self.start_time) * 1000
        
        # Ensure all expected keys exist (with 0 defaults)
        # NOTE: rate_limit_email_ms/ip_ms removed - combined mode uses only rate_limit_total_ms
        # Cache field names use "login_user_cache_" prefix for clarity
        default_timings = [
            "rate_limit_total_ms",
            "rate_limit_reset_ms",
            "redis_rtt_ms",
            "login_user_cache_get_ms",
            "login_user_cache_set_ms",
            "password_hash_lookup_ms",
            "lookup_user_ms",
            "argon2_verify_ms",
            "legacy_ssot_fix_ms",
            "issue_token_ms",
            "session_create_ms",
            "backoff_ms",
            "activation_check_ms",
        ]
        for key in default_timings:
            self.timings.setdefault(key, 0.0)
        
        # NOTE: No fallback calculation for rate_limit_total_ms
        # In combined mode, it MUST be set explicitly from rl_decision.timings["total_ms"]
        
        # Set request.state for timing_middleware
        if request is not None:
            try:
                request.state.db_exec_ms = self.timings.get("lookup_user_ms", 0)
                request.state.rate_limit_total_ms = self.timings.get("rate_limit_total_ms", 0)
                # Full timings for observability (NOT serialized to response)
                request.state.login_timings = self.timings.copy()
                
                # ═══════════════════════════════════════════════════════════════
                # Aligned with RequestTelemetry.finalize(): set route_handler_ms
                # total_ms includes everything measured (DB, argon2, rate limit, etc.)
                # ═══════════════════════════════════════════════════════════════
                request.state.route_handler_ms = float(self.timings.get("total_ms", 0.0))
                
            except Exception as e:
                logger.debug("Failed to set request.state: %s", str(e))
        
        # Emit structured log
        self._emit_log(result)
        
        return self._build_summary()
    
    def _build_summary(self) -> Dict[str, Any]:
        """Build summary dict with all timings and flags."""
        return {
            "timings": self.timings.copy(),
            "flags": self.flags.copy(),
        }
    
    def _emit_log(self, result: LoginResult) -> None:
        """
        Emit single structured log event.
        
        Rules:
        - INFO if: slow (>= threshold) OR legacy_ssot_fix OR error/rate_limited
        - DEBUG for fast successful logins
        - Force INFO if LOGIN_TELEMETRY_DEBUG is enabled
        """
        total_ms = self.timings.get("total_ms", 0)
        used_legacy_ssot_fix = self.flags.get("used_legacy_ssot_fix", False)
        is_error = result not in ("success",)
        is_slow = total_ms >= SLOW_LOGIN_THRESHOLD_MS
        
        # Rate limit instrumentation details
        rate_limit_roundtrips = self.flags.get("rate_limit_roundtrips", 0)
        
        log_msg = (
            "login_timing_breakdown email=%s mode=%s result=%s "
            "auth_user_id_present=%s used_legacy_ssot_fix=%s login_user_cache_hit=%s early_reject=%s "
            "total_ms=%.2f login_user_cache_get_ms=%.2f password_hash_lookup_ms=%.2f lookup_user_ms=%.2f "
            "argon2_verify_ms=%.2f legacy_ssot_fix_ms=%.2f issue_token_ms=%.2f session_create_ms=%.2f "
            "rate_limit_total_ms=%.2f redis_rtt_ms=%.2f rate_limit_reset_ms=%.2f "
            "rate_limit_roundtrips=%d backoff_ms=%.2f login_user_cache_set_ms=%.2f"
        )
        log_args = (
            self.email_masked,
            self.flags.get("mode", "core_login"),
            result,
            self.flags.get("auth_user_id_present", False),
            used_legacy_ssot_fix,
            self.flags.get("login_user_cache_hit", False),
            self.flags.get("early_reject", False),
            total_ms,
            self.timings.get("login_user_cache_get_ms", 0),
            self.timings.get("password_hash_lookup_ms", 0),
            self.timings.get("lookup_user_ms", 0),
            self.timings.get("argon2_verify_ms", 0),
            self.timings.get("legacy_ssot_fix_ms", 0),
            self.timings.get("issue_token_ms", 0),
            self.timings.get("session_create_ms", 0),
            self.timings.get("rate_limit_total_ms", 0),
            self.timings.get("redis_rtt_ms", 0),
            self.timings.get("rate_limit_reset_ms", 0),
            rate_limit_roundtrips,
            self.timings.get("backoff_ms", 0),
            self.timings.get("login_user_cache_set_ms", 0),
        )
        
        # Determine log level
        use_info = (
            LOGIN_TELEMETRY_DEBUG or
            is_slow or
            used_legacy_ssot_fix or
            is_error
        )
        
        if use_info:
            logger.info(log_msg, *log_args)
        else:
            logger.debug(log_msg, *log_args)


__all__ = ["LoginTelemetry", "LoginResult", "SLOW_LOGIN_THRESHOLD_MS"]
