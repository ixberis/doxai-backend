# -*- coding: utf-8 -*-
"""
backend/app/shared/security/login_cache_metrics.py

Prometheus metrics for login user cache.

Metrics are AGGREGATE ONLY - no PII (no email, no auth_user_id).

Design principles:
- Single point of instrumentation per event
- Strict cardinality control (finite label values)
- Thread-safe get_or_create pattern for multi-worker/test scenarios
- Registry injection for test isolation

Counters:
- login_user_cache_hit_total
- login_user_cache_miss_total
- login_user_cache_early_reject_total (labeled by reason)
- login_user_cache_error_total (labeled by error_type)

Histograms:
- login_user_cache_get_seconds
- login_user_cache_set_seconds
- login_password_hash_lookup_seconds

Autor: DoxAI
Fecha: 2026-01-12
"""
from __future__ import annotations

import logging
from typing import Optional, Set

from prometheus_client import CollectorRegistry, REGISTRY

from app.shared.core.metrics_helpers import (
    get_or_create_counter,
    get_or_create_histogram,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# STRICT CARDINALITY CONTROL
# ─────────────────────────────────────────────────────────────────────────────

# Valid error_type labels (finite set)
VALID_ERROR_TYPES: Set[str] = frozenset({
    "redis_unavailable",
    "redis_error",
    "deserialize_error",
    "cache_disabled",
    "set_error",
    "unexpected",
})

# Valid early_reject reason labels (finite set)
# Includes "unexpected" to avoid hiding bugs with silent defaults
VALID_EARLY_REJECT_REASONS: Set[str] = frozenset({
    "not_activated",
    "deleted",
    "unexpected",
})


def _normalize_error_type(error_type: str) -> str:
    """
    Normalize error_type to valid label value.
    
    Unknown error types map to 'unexpected' to prevent cardinality explosion.
    Exception messages should NEVER be used as labels - log them instead.
    """
    if error_type in VALID_ERROR_TYPES:
        return error_type
    # Log the actual error for debugging, but use normalized label
    logger.debug(
        "login_cache_metrics_unknown_error_type raw=%s normalized=unexpected",
        error_type[:50] if error_type else "empty",
    )
    return "unexpected"


def _normalize_early_reject_reason(reason: str) -> str:
    """
    Normalize early_reject reason to valid label value.
    
    Known mappings for legacy/variant names:
    - account_not_activated, inactive -> not_activated
    - account_deleted, soft_deleted -> deleted
    
    Unknown values -> "unexpected" (no silent defaults to avoid hiding bugs)
    """
    if reason in VALID_EARLY_REJECT_REASONS:
        return reason
    # Map legacy/variant names to canonical values
    if reason in ("account_not_activated", "inactive"):
        return "not_activated"
    if reason in ("account_deleted", "soft_deleted"):
        return "deleted"
    # IMPORTANT: Unknown values -> "unexpected" to surface bugs
    logger.warning(
        "login_cache_metrics_unknown_early_reject_reason raw=%s normalized=unexpected",
        reason,
    )
    return "unexpected"


# ─────────────────────────────────────────────────────────────────────────────
# COUNTERS (no labels with PII)
# Uses get_or_create pattern for safe multi-import
# ─────────────────────────────────────────────────────────────────────────────

LOGIN_USER_CACHE_HIT = get_or_create_counter(
    "login_user_cache_hit_total",
    "Total login user cache hits",
)

LOGIN_USER_CACHE_MISS = get_or_create_counter(
    "login_user_cache_miss_total",
    "Total login user cache misses",
)

LOGIN_USER_CACHE_EARLY_REJECT = get_or_create_counter(
    "login_user_cache_early_reject_total",
    "Total early rejects from cached user state",
    labelnames=("reason",),  # "not_activated", "deleted"
)

LOGIN_USER_CACHE_ERROR = get_or_create_counter(
    "login_user_cache_error_total",
    "Total login user cache errors (fail-open)",
    labelnames=("error_type",),  # finite set from VALID_ERROR_TYPES
)


# ─────────────────────────────────────────────────────────────────────────────
# HISTOGRAMS (latency in seconds for Prometheus convention)
# ─────────────────────────────────────────────────────────────────────────────

LOGIN_USER_CACHE_GET_LATENCY = get_or_create_histogram(
    "login_user_cache_get_seconds",
    "Login user cache GET latency (seconds)",
)

LOGIN_USER_CACHE_SET_LATENCY = get_or_create_histogram(
    "login_user_cache_set_seconds",
    "Login user cache SET latency (seconds)",
)

LOGIN_PASSWORD_HASH_LOOKUP_LATENCY = get_or_create_histogram(
    "login_password_hash_lookup_seconds",
    "Password hash PK lookup latency (seconds)",
)


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions for instrumentation (SINGLE POINT OF CALL)
#
# These are the ONLY functions that should increment metrics.
# login_user_cache.py calls observe_* for GET/SET latency only.
# login_flow_service.py calls record_* for hit/miss/error/early_reject.
# ─────────────────────────────────────────────────────────────────────────────

def record_cache_hit() -> None:
    """Record a cache hit. Call once per cache GET that returns data."""
    LOGIN_USER_CACHE_HIT.inc()


def record_cache_miss() -> None:
    """Record a cache miss. Call once per cache GET that returns no data."""
    LOGIN_USER_CACHE_MISS.inc()


def record_early_reject(reason: str) -> None:
    """
    Record an early reject from cached user state.
    
    Args:
        reason: "not_activated" or "deleted" (normalized automatically)
    """
    normalized = _normalize_early_reject_reason(reason)
    LOGIN_USER_CACHE_EARLY_REJECT.labels(reason=normalized).inc()


def record_cache_error(error_type: str) -> None:
    """
    Record a cache error (fail-open scenario).
    
    Args:
        error_type: One of VALID_ERROR_TYPES (normalized automatically)
        
    IMPORTANT: Never pass exception messages as error_type.
    Log the exception separately for debugging.
    """
    normalized = _normalize_error_type(error_type)
    LOGIN_USER_CACHE_ERROR.labels(error_type=normalized).inc()


def observe_cache_get_latency(duration_seconds: float) -> None:
    """
    Observe cache GET latency.
    
    Args:
        duration_seconds: Duration in seconds
    """
    LOGIN_USER_CACHE_GET_LATENCY.observe(duration_seconds)


def observe_cache_set_latency(duration_seconds: float) -> None:
    """
    Observe cache SET latency.
    
    Args:
        duration_seconds: Duration in seconds
    """
    LOGIN_USER_CACHE_SET_LATENCY.observe(duration_seconds)


def observe_password_hash_lookup_latency(duration_seconds: float) -> None:
    """
    Observe password hash PK lookup latency.
    
    Args:
        duration_seconds: Duration in seconds
    """
    LOGIN_PASSWORD_HASH_LOOKUP_LATENCY.observe(duration_seconds)


# ─────────────────────────────────────────────────────────────────────────────
# Test helpers (isolated registry)
# ─────────────────────────────────────────────────────────────────────────────

class IsolatedLoginCacheMetrics:
    """
    Isolated metrics for testing.
    
    Creates metrics in a separate CollectorRegistry to avoid pollution
    of the global registry and duplicate timeseries errors.
    
    Usage:
        metrics = IsolatedLoginCacheMetrics()
        metrics.record_cache_hit()
        assert metrics.hit_count() == 1
    """
    
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        from prometheus_client import Counter, Histogram
        
        self.registry = registry or CollectorRegistry()
        
        # Create isolated counters
        self.cache_hit = Counter(
            "login_user_cache_hit_total",
            "Total login user cache hits",
            registry=self.registry,
        )
        self.cache_miss = Counter(
            "login_user_cache_miss_total",
            "Total login user cache misses",
            registry=self.registry,
        )
        self.early_reject = Counter(
            "login_user_cache_early_reject_total",
            "Total early rejects",
            labelnames=("reason",),
            registry=self.registry,
        )
        self.cache_error = Counter(
            "login_user_cache_error_total",
            "Total cache errors",
            labelnames=("error_type",),
            registry=self.registry,
        )
        
        # Create isolated histograms
        self.get_latency = Histogram(
            "login_user_cache_get_seconds",
            "GET latency",
            registry=self.registry,
        )
        self.set_latency = Histogram(
            "login_user_cache_set_seconds",
            "SET latency",
            registry=self.registry,
        )
        self.pk_lookup_latency = Histogram(
            "login_password_hash_lookup_seconds",
            "PK lookup latency",
            registry=self.registry,
        )
    
    def record_cache_hit(self) -> None:
        self.cache_hit.inc()
    
    def record_cache_miss(self) -> None:
        self.cache_miss.inc()
    
    def record_early_reject(self, reason: str) -> None:
        normalized = _normalize_early_reject_reason(reason)
        self.early_reject.labels(reason=normalized).inc()
    
    def record_cache_error(self, error_type: str) -> None:
        normalized = _normalize_error_type(error_type)
        self.cache_error.labels(error_type=normalized).inc()
    
    def observe_cache_get_latency(self, seconds: float) -> None:
        self.get_latency.observe(seconds)
    
    def observe_cache_set_latency(self, seconds: float) -> None:
        self.set_latency.observe(seconds)
    
    def observe_password_hash_lookup_latency(self, seconds: float) -> None:
        self.pk_lookup_latency.observe(seconds)
    
    # ─── Accessors for assertions ───
    
    def hit_count(self) -> float:
        return self.cache_hit._value.get()
    
    def miss_count(self) -> float:
        return self.cache_miss._value.get()
    
    def early_reject_count(self, reason: str) -> float:
        normalized = _normalize_early_reject_reason(reason)
        return self.early_reject.labels(reason=normalized)._value.get()
    
    def error_count(self, error_type: str) -> float:
        normalized = _normalize_error_type(error_type)
        return self.cache_error.labels(error_type=normalized)._value.get()
    
    def get_latency_count(self) -> int:
        return int(self.get_latency._count.get())
    
    def set_latency_count(self) -> int:
        return int(self.set_latency._count.get())
    
    def pk_lookup_latency_count(self) -> int:
        return int(self.pk_lookup_latency._count.get())


__all__ = [
    # Counters
    "LOGIN_USER_CACHE_HIT",
    "LOGIN_USER_CACHE_MISS",
    "LOGIN_USER_CACHE_EARLY_REJECT",
    "LOGIN_USER_CACHE_ERROR",
    # Histograms
    "LOGIN_USER_CACHE_GET_LATENCY",
    "LOGIN_USER_CACHE_SET_LATENCY",
    "LOGIN_PASSWORD_HASH_LOOKUP_LATENCY",
    # Helper functions (single instrumentation point)
    "record_cache_hit",
    "record_cache_miss",
    "record_early_reject",
    "record_cache_error",
    "observe_cache_get_latency",
    "observe_cache_set_latency",
    "observe_password_hash_lookup_latency",
    # Cardinality control
    "VALID_ERROR_TYPES",
    "VALID_EARLY_REJECT_REASONS",
    # Test helpers
    "IsolatedLoginCacheMetrics",
]
