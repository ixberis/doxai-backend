# -*- coding: utf-8 -*-
"""
backend/app/shared/security/auth_context_cache.py

Cache de contexto de autenticación en Redis para reducir lookup_user_ms.
Read-through cache con TTL corto para AuthContextDTO.

Features:
- TTL configurable via AUTH_CTX_CACHE_TTL_SECONDS (default 60s)
- Read-through: GET primero, si miss -> DB -> SETEX
- Invalidación explícita para cambios de usuario
- Best-effort: si Redis falla, fallback a DB sin errores
- Uses canonical Redis client from app.shared.redis

Autor: DoxAI
Fecha: 2026-01-12
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

# TTL configurable (default 60 seconds)
AUTH_CTX_CACHE_TTL_SECONDS = int(os.getenv("AUTH_CTX_CACHE_TTL_SECONDS", "60"))

# Key prefix
AUTH_CTX_KEY_PREFIX = "auth_user_ctx"

# Debug flag for verbose logging
AUTH_CTX_CACHE_DEBUG = os.getenv("AUTH_CTX_CACHE_DEBUG", "0").lower() in ("1", "true", "yes")


@dataclass
class AuthCtxCacheResult:
    """Resultado de operación de cache."""
    cache_hit: bool
    duration_ms: float
    error: Optional[str] = None


def _build_cache_key(auth_user_id: UUID) -> str:
    """Build Redis key for auth context cache."""
    return f"{AUTH_CTX_KEY_PREFIX}:{str(auth_user_id)}"


def _serialize_auth_context(ctx: "AuthContextDTO") -> str:
    """
    Serialize AuthContextDTO to JSON for Redis storage.
    
    Only stores minimal, non-sensitive fields needed for auth:
    - user_id, auth_user_id, user_email
    - user_role, user_status, user_is_activated
    - deleted_at
    
    NO sensitive data: tokens, password hashes, etc.
    """
    data = {
        "user_id": ctx.user_id,
        "auth_user_id": str(ctx.auth_user_id),
        "user_email": ctx.user_email,
        "user_role": ctx.user_role,
        "user_status": ctx.user_status,
        "user_is_activated": ctx.user_is_activated,
        "deleted_at": ctx.deleted_at.isoformat() if ctx.deleted_at else None,
    }
    return json.dumps(data)


def _deserialize_auth_context(data: str) -> Optional[Dict[str, Any]]:
    """
    Deserialize JSON from Redis to dict for AuthContextDTO.from_mapping.
    
    Returns dict or None if parsing fails.
    """
    try:
        parsed = json.loads(data)
        # Convert auth_user_id back to UUID
        if "auth_user_id" in parsed and parsed["auth_user_id"]:
            parsed["auth_user_id"] = UUID(parsed["auth_user_id"])
        # Convert deleted_at back to datetime
        if parsed.get("deleted_at"):
            parsed["deleted_at"] = datetime.fromisoformat(parsed["deleted_at"])
        return parsed
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning("auth_ctx_cache_deserialize_failed error=%s", str(e))
        return None


class AuthContextCache:
    """
    Cache de contexto de autenticación en Redis.
    
    Uses canonical Redis client from app.shared.redis.
    """
    
    _instance: Optional["AuthContextCache"] = None
    
    @classmethod
    def get_instance(cls) -> "AuthContextCache":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None
    
    def __init__(self):
        self._enabled = os.getenv("AUTH_CTX_CACHE_ENABLED", "true").lower() == "true"
        self._ttl = AUTH_CTX_CACHE_TTL_SECONDS
    
    async def _get_redis_client(self) -> Optional[Any]:
        """
        Get async Redis client from canonical shared module.
        
        Returns None if Redis not available.
        """
        try:
            from app.shared.redis import get_async_redis_client
            return await get_async_redis_client()
        except Exception:
            return None
    
    async def get_cached(
        self, auth_user_id: UUID
    ) -> tuple[Optional[Dict[str, Any]], AuthCtxCacheResult]:
        """
        Get cached auth context from Redis.
        
        Args:
            auth_user_id: UUID of the user
            
        Returns:
            Tuple of (dict for AuthContextDTO.from_mapping or None, result with timing)
        """
        start = time.perf_counter()
        result = AuthCtxCacheResult(cache_hit=False, duration_ms=0)
        
        if not self._enabled:
            result.duration_ms = (time.perf_counter() - start) * 1000
            result.error = "cache_disabled"
            if AUTH_CTX_CACHE_DEBUG:
                logger.debug(
                    "auth_ctx_cache_skip reason=disabled auth_user_id=%s",
                    str(auth_user_id)[:8] + "...",
                )
            return None, result
        
        try:
            client = await self._get_redis_client()
            if not client:
                result.duration_ms = (time.perf_counter() - start) * 1000
                result.error = "redis_not_available"
                logger.debug(
                    "auth_ctx_cache_skip reason=redis_unavailable auth_user_id=%s",
                    str(auth_user_id)[:8] + "...",
                )
                return None, result
            
            key = _build_cache_key(auth_user_id)
            cached_data = await client.get(key)
            
            result.duration_ms = (time.perf_counter() - start) * 1000
            
            if cached_data is None:
                # Cache miss - DEBUG level only (no spam)
                result.error = "key_not_found"
                if AUTH_CTX_CACHE_DEBUG and logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "auth_ctx_cache_miss auth_user_id=%s reason=key_not_found duration_ms=%.2f",
                        str(auth_user_id)[:8] + "...",
                        result.duration_ms,
                    )
                return None, result
            
            # Parse cached data
            mapping = _deserialize_auth_context(cached_data)
            if mapping is None:
                result.error = "deserialize_failed"
                if AUTH_CTX_CACHE_DEBUG:
                    logger.warning(
                        "auth_ctx_cache_miss auth_user_id=%s reason=deserialize_failed duration_ms=%.2f",
                        str(auth_user_id)[:8] + "...",
                        result.duration_ms,
                    )
                return None, result
            
            result.cache_hit = True
            
            # Log cache hit (DEBUG level for production, INFO if debug enabled)
            log_level = logging.INFO if AUTH_CTX_CACHE_DEBUG else logging.DEBUG
            if logger.isEnabledFor(log_level):
                logger.log(
                    log_level,
                    "auth_ctx_cache_hit auth_user_id=%s duration_ms=%.2f ttl=%d",
                    str(auth_user_id)[:8] + "...",
                    result.duration_ms,
                    self._ttl,
                )
            
            return mapping, result
            
        except Exception as e:
            result.duration_ms = (time.perf_counter() - start) * 1000
            result.error = str(e)
            logger.warning(
                "auth_ctx_cache_get_failed auth_user_id=%s error=%s duration_ms=%.2f",
                str(auth_user_id)[:8] + "...",
                str(e),
                result.duration_ms,
            )
            return None, result
    
    async def set_cached(
        self, auth_user_id: UUID, ctx: "AuthContextDTO"
    ) -> AuthCtxCacheResult:
        """
        Store auth context in Redis cache with TTL.
        
        CRITICAL: Always logs set_success or set_failed at INFO level for
        production diagnostics. This is essential to verify the cache
        is being populated correctly.
        
        Args:
            auth_user_id: UUID of the user
            ctx: AuthContextDTO to cache
            
        Returns:
            AuthCtxCacheResult with timing and success/error info
        """
        start = time.perf_counter()
        result = AuthCtxCacheResult(cache_hit=False, duration_ms=0)
        auth_id_prefix = str(auth_user_id)[:8] + "..."
        
        if not self._enabled:
            result.duration_ms = (time.perf_counter() - start) * 1000
            result.error = "cache_disabled"
            # DEBUG level to avoid log spam in production
            if AUTH_CTX_CACHE_DEBUG:
                logger.info(
                    "auth_ctx_cache_set_skipped auth_user_id=%s reason=cache_disabled",
                    auth_id_prefix,
                )
            else:
                logger.debug(
                    "auth_ctx_cache_set_skipped auth_user_id=%s reason=cache_disabled",
                    auth_id_prefix,
                )
            return result
        
        try:
            client = await self._get_redis_client()
            if not client:
                result.duration_ms = (time.perf_counter() - start) * 1000
                result.error = "redis_not_available"
                # WARNING level for infrastructure issues
                logger.warning(
                    "auth_ctx_cache_set_failed auth_user_id=%s error=redis_not_available",
                    auth_id_prefix,
                )
                return result
            
            key = _build_cache_key(auth_user_id)
            serialized = _serialize_auth_context(ctx)
            
            await client.setex(key, self._ttl, serialized)
            
            result.duration_ms = (time.perf_counter() - start) * 1000
            
            # DEBUG by default, INFO only with AUTH_CTX_CACHE_DEBUG=1
            if AUTH_CTX_CACHE_DEBUG:
                logger.info(
                    "auth_ctx_cache_set_success auth_user_id=%s ttl=%d duration_ms=%.2f",
                    auth_id_prefix,
                    self._ttl,
                    result.duration_ms,
                )
            else:
                logger.debug(
                    "auth_ctx_cache_set_success auth_user_id=%s ttl=%d duration_ms=%.2f",
                    auth_id_prefix,
                    self._ttl,
                    result.duration_ms,
                )
            
            return result
            
        except Exception as e:
            result.duration_ms = (time.perf_counter() - start) * 1000
            result.error = str(e)
            # WARNING level for errors
            logger.warning(
                "auth_ctx_cache_set_failed auth_user_id=%s error=%s duration_ms=%.2f",
                auth_id_prefix,
                str(e)[:50],  # Truncate error message
                result.duration_ms,
            )
            return result
    
    async def invalidate(self, auth_user_id: UUID) -> AuthCtxCacheResult:
        """
        Invalidate (delete) cached auth context for a user.
        
        Call this when user data changes (role, status, activation, delete).
        
        Args:
            auth_user_id: UUID of the user to invalidate
            
        Returns:
            AuthCtxCacheResult with timing
        """
        start = time.perf_counter()
        result = AuthCtxCacheResult(cache_hit=False, duration_ms=0)
        
        if not self._enabled:
            result.duration_ms = (time.perf_counter() - start) * 1000
            return result
        
        try:
            client = await self._get_redis_client()
            if not client:
                result.duration_ms = (time.perf_counter() - start) * 1000
                result.error = "redis_not_available"
                return result
            
            key = _build_cache_key(auth_user_id)
            deleted = await client.delete(key)
            
            result.duration_ms = (time.perf_counter() - start) * 1000
            
            if deleted:
                logger.debug(
                    "auth_ctx_cache_invalidated auth_user_id=%s duration_ms=%.2f",
                    str(auth_user_id)[:8] + "...",
                    result.duration_ms,
                )
            
            return result
            
        except Exception as e:
            result.duration_ms = (time.perf_counter() - start) * 1000
            result.error = str(e)
            # Best-effort: log at DEBUG level, not WARNING
            logger.debug(
                "auth_ctx_cache_invalidate_failed auth_user_id=%s error=%s",
                str(auth_user_id)[:8] + "...",
                str(e),
            )
            return result


def get_auth_context_cache() -> AuthContextCache:
    """Get singleton auth context cache."""
    return AuthContextCache.get_instance()


# ─────────────────────────────────────────────────────────────────────────────
# Invalidation helper for use in services
# ─────────────────────────────────────────────────────────────────────────────

async def invalidate_auth_context_cache(auth_user_id: UUID) -> None:
    """
    Helper to invalidate auth context cache for a user.
    
    Call this from services when user data changes:
    - user_status change
    - user_role change
    - deleted_at change (soft delete)
    - user_is_activated change
    
    Best-effort: silently ignores errors.
    """
    try:
        cache = get_auth_context_cache()
        await cache.invalidate(auth_user_id)
    except Exception:
        pass  # Best-effort, silent


__all__ = [
    "AuthContextCache",
    "AuthCtxCacheResult",
    "get_auth_context_cache",
    "invalidate_auth_context_cache",
    "AUTH_CTX_CACHE_TTL_SECONDS",
]
