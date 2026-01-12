# -*- coding: utf-8 -*-
"""
backend/app/shared/security/__init__.py

Security utilities for DoxAI.
"""

from .rate_limit_service import RateLimitService, RateLimitResult, get_rate_limiter
from .rate_limit_dep import RateLimitDep, RateLimitExceeded, check_rate_limit, rate_limit_response
from .redis_warmup import warmup_redis_async, RedisWarmupResult
from .auth_context_cache import (
    AuthContextCache,
    AuthCtxCacheResult,
    get_auth_context_cache,
    invalidate_auth_context_cache,
    AUTH_CTX_CACHE_TTL_SECONDS,
)
from .login_user_cache import (
    LoginUserCache,
    LoginUserCacheData,
    LoginUserCacheResult,
    get_login_user_cache,
    invalidate_login_user_cache,
    LOGIN_USER_CACHE_TTL_SECONDS,
)
from .login_cache_warmup import (
    warmup_login_cache_async,
    LoginCacheWarmupResult,
)
from .login_cache_metrics import (
    LOGIN_USER_CACHE_HIT,
    LOGIN_USER_CACHE_MISS,
    LOGIN_USER_CACHE_EARLY_REJECT,
    LOGIN_USER_CACHE_ERROR,
    LOGIN_USER_CACHE_GET_LATENCY,
    LOGIN_USER_CACHE_SET_LATENCY,
    LOGIN_PASSWORD_HASH_LOOKUP_LATENCY,
    record_cache_hit,
    record_cache_miss,
    record_early_reject,
    record_cache_error,
    observe_cache_get_latency,
    observe_cache_set_latency,
    observe_password_hash_lookup_latency,
    VALID_ERROR_TYPES,
    VALID_EARLY_REJECT_REASONS,
    IsolatedLoginCacheMetrics,
)

__all__ = [
    "RateLimitService",
    "RateLimitResult", 
    "get_rate_limiter",
    "RateLimitDep",
    "RateLimitExceeded",
    "check_rate_limit",
    "rate_limit_response",
    "warmup_redis_async",
    "RedisWarmupResult",
    "AuthContextCache",
    "AuthCtxCacheResult",
    "get_auth_context_cache",
    "invalidate_auth_context_cache",
    "AUTH_CTX_CACHE_TTL_SECONDS",
    "LoginUserCache",
    "LoginUserCacheData",
    "LoginUserCacheResult",
    "get_login_user_cache",
    "invalidate_login_user_cache",
    "LOGIN_USER_CACHE_TTL_SECONDS",
    "warmup_login_cache_async",
    "LoginCacheWarmupResult",
    # Prometheus metrics
    "LOGIN_USER_CACHE_HIT",
    "LOGIN_USER_CACHE_MISS",
    "LOGIN_USER_CACHE_EARLY_REJECT",
    "LOGIN_USER_CACHE_ERROR",
    "LOGIN_USER_CACHE_GET_LATENCY",
    "LOGIN_USER_CACHE_SET_LATENCY",
    "LOGIN_PASSWORD_HASH_LOOKUP_LATENCY",
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
