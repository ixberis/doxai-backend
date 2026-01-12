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
]
