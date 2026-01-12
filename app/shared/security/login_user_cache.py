# -*- coding: utf-8 -*-
"""
backend/app/shared/security/login_user_cache.py

Cache de usuario para login optimizado en Redis.
Almacena SOLO datos no sensibles para acelerar lookup:
- user_id, auth_user_id (identificadores)
- user_status, user_is_activated, deleted_at (para early reject)

NO ALMACENA: password_hash, user_email, user_full_name (seguridad/mínimo)

El flujo de login con cache:
1. Redis GET login_user:{hmac_email}
2. HIT: Early reject si deleted/not_activated, luego PK lookup para password_hash
3. MISS: Full email lookup → SET cache

Autor: DoxAI
Fecha: 2026-01-12
Updated: 2026-01-12 - Payload mínimo + HMAC key hardening
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

# TTL configurable (default 120 seconds - mayor que auth_ctx porque login es menos frecuente)
LOGIN_USER_CACHE_TTL_SECONDS = int(os.getenv("LOGIN_USER_CACHE_TTL_SECONDS", "120"))

# Key prefix
LOGIN_USER_KEY_PREFIX = "login_user"

# Debug flag for verbose logging
LOGIN_USER_CACHE_DEBUG = os.getenv("LOGIN_USER_CACHE_DEBUG", "0").lower() in ("1", "true", "yes")

# Secret for HMAC key derivation (optional, falls back to SHA256 if not set)
LOGIN_USER_CACHE_KEY_SECRET = os.getenv("LOGIN_USER_CACHE_KEY_SECRET", "")


@dataclass
class LoginUserCacheData:
    """
    Datos cacheados para login (NO incluye password_hash, email, full_name - son PII).
    
    Payload MÍNIMO para:
    1. Early reject (status checks)
    2. Lookup por PK para password_hash
    3. Response building (user_role - no es PII)
    
    NOTA: user_role se incluye porque NO es PII y es necesario para:
    - Claims del JWT
    - Response de login
    - Validación de permisos
    """
    user_id: int
    auth_user_id: UUID
    user_status: str
    user_is_activated: bool
    user_role: str = "user"  # Default seguro, no PII
    deleted_at: Optional[datetime] = None
    
    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
    
    @property
    def can_proceed_to_password_check(self) -> bool:
        """True si el usuario puede pasar a verificación de password."""
        return self.user_is_activated and not self.is_deleted


@dataclass
class LoginUserCacheResult:
    """Resultado de operación de cache con métricas."""
    cache_hit: bool
    duration_ms: float
    early_reject: bool = False
    early_reject_reason: Optional[str] = None
    error: Optional[str] = None
    fallback_reason: Optional[str] = None


def _hash_email_for_key(email: str) -> str:
    """
    Hash del email para usar como clave de Redis.
    
    Si LOGIN_USER_CACHE_KEY_SECRET está configurado, usa HMAC-SHA256.
    Sino, usa SHA256 truncado (fallback).
    
    El email ya está normalizado (lower/strip) antes de llegar aquí.
    """
    email_bytes = email.encode("utf-8")
    
    if LOGIN_USER_CACHE_KEY_SECRET:
        # HMAC-SHA256 con secret
        secret_bytes = LOGIN_USER_CACHE_KEY_SECRET.encode("utf-8")
        return hmac.new(secret_bytes, email_bytes, hashlib.sha256).hexdigest()[:32]
    else:
        # Fallback: SHA256 simple
        return hashlib.sha256(email_bytes).hexdigest()[:32]


def _build_cache_key(email: str) -> str:
    """Build Redis key for login user cache."""
    email_hash = _hash_email_for_key(email)
    return f"{LOGIN_USER_KEY_PREFIX}:{email_hash}"


def _serialize_login_user_data(data: LoginUserCacheData) -> str:
    """
    Serialize LoginUserCacheData to JSON for Redis storage.
    
    PAYLOAD MÍNIMO: user_id, auth_user_id, user_status, user_is_activated, user_role, deleted_at
    NO incluye: password_hash, user_email, user_full_name (PII)
    
    NOTA: user_role se incluye porque NO es PII y es necesario para JWT claims.
    """
    payload = {
        "user_id": data.user_id,
        "auth_user_id": str(data.auth_user_id),
        "user_status": data.user_status,
        "user_is_activated": data.user_is_activated,
        "user_role": data.user_role,
        "deleted_at": data.deleted_at.isoformat() if data.deleted_at else None,
    }
    return json.dumps(payload)


def _deserialize_login_user_data(raw: str) -> Optional[LoginUserCacheData]:
    """
    Deserialize JSON from Redis to LoginUserCacheData.
    
    PAYLOAD MÍNIMO: user_id, auth_user_id, user_status, user_is_activated, user_role, deleted_at
    Returns None if parsing fails.
    
    NOTA: user_role tiene fallback a "user" para compatibilidad con cache entries antiguas.
    """
    try:
        parsed = json.loads(raw)
        
        # Convert types
        auth_user_id = UUID(parsed["auth_user_id"]) if parsed.get("auth_user_id") else None
        if auth_user_id is None:
            return None  # auth_user_id is required
        
        deleted_at = None
        if parsed.get("deleted_at"):
            deleted_at = datetime.fromisoformat(parsed["deleted_at"])
        
        # user_role fallback para cache entries antiguas sin este campo
        user_role = parsed.get("user_role", "user")
        
        return LoginUserCacheData(
            user_id=int(parsed["user_id"]),
            auth_user_id=auth_user_id,
            user_status=parsed["user_status"],
            user_is_activated=bool(parsed["user_is_activated"]),
            user_role=user_role,
            deleted_at=deleted_at,
        )
    except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
        logger.warning("login_user_cache_deserialize_failed error=%s", str(e))
        return None


class LoginUserCache:
    """
    Cache de usuario para login en Redis.
    
    Uses canonical Redis client from app.shared.redis.
    """
    
    _instance: Optional["LoginUserCache"] = None
    
    @classmethod
    def get_instance(cls) -> "LoginUserCache":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None
    
    def __init__(self):
        self._enabled = os.getenv("LOGIN_USER_CACHE_ENABLED", "true").lower() == "true"
        self._ttl = LOGIN_USER_CACHE_TTL_SECONDS
    
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
        self, email: str
    ) -> tuple[Optional[LoginUserCacheData], LoginUserCacheResult]:
        """
        Get cached login user data from Redis.
        
        Args:
            email: Normalized email (lower/stripped)
            
        Returns:
            Tuple of (LoginUserCacheData or None, result with timing)
        """
        start = time.perf_counter()
        result = LoginUserCacheResult(cache_hit=False, duration_ms=0)
        
        if not self._enabled:
            result.duration_ms = (time.perf_counter() - start) * 1000
            result.fallback_reason = "cache_disabled"
            return None, result
        
        try:
            client = await self._get_redis_client()
            if not client:
                result.duration_ms = (time.perf_counter() - start) * 1000
                result.error = "redis_not_available"
                result.fallback_reason = "redis_unavailable"
                return None, result
            
            key = _build_cache_key(email)
            cached_data = await client.get(key)
            
            result.duration_ms = (time.perf_counter() - start) * 1000
            
            if cached_data is None:
                if LOGIN_USER_CACHE_DEBUG and logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "login_user_cache_miss email_hash=%s duration_ms=%.2f",
                        _hash_email_for_key(email)[:8] + "...",
                        result.duration_ms,
                    )
                result.fallback_reason = "cache_miss"
                return None, result
            
            # Parse cached data
            data = _deserialize_login_user_data(cached_data)
            if data is None:
                result.error = "deserialize_failed"
                result.fallback_reason = "deserialize_error"
                return None, result
            
            result.cache_hit = True
            
            if LOGIN_USER_CACHE_DEBUG and logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "login_user_cache_hit user_id=%s duration_ms=%.2f",
                    data.user_id,
                    result.duration_ms,
                )
            
            return data, result
            
        except Exception as e:
            result.duration_ms = (time.perf_counter() - start) * 1000
            result.error = str(e)
            result.fallback_reason = "redis_error"
            logger.warning(
                "login_user_cache_get_failed email_hash=%s error=%s duration_ms=%.2f",
                _hash_email_for_key(email)[:8] + "...",
                str(e),
                result.duration_ms,
            )
            return None, result
    
    async def set_cached(
        self, email: str, data: LoginUserCacheData
    ) -> LoginUserCacheResult:
        """
        Store login user data in Redis cache with TTL (best-effort).
        
        Args:
            email: Normalized email
            data: LoginUserCacheData to cache (NO password_hash)
            
        Returns:
            LoginUserCacheResult with timing
        """
        start = time.perf_counter()
        result = LoginUserCacheResult(cache_hit=False, duration_ms=0)
        
        if not self._enabled:
            result.duration_ms = (time.perf_counter() - start) * 1000
            return result
        
        try:
            client = await self._get_redis_client()
            if not client:
                result.duration_ms = (time.perf_counter() - start) * 1000
                result.error = "redis_not_available"
                return result
            
            key = _build_cache_key(email)
            serialized = _serialize_login_user_data(data)
            
            await client.setex(key, self._ttl, serialized)
            
            result.duration_ms = (time.perf_counter() - start) * 1000
            
            if LOGIN_USER_CACHE_DEBUG and logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "login_user_cache_set user_id=%s ttl=%d duration_ms=%.2f",
                    data.user_id,
                    self._ttl,
                    result.duration_ms,
                )
            
            return result
            
        except Exception as e:
            result.duration_ms = (time.perf_counter() - start) * 1000
            result.error = str(e)
            logger.debug(
                "login_user_cache_set_failed email_hash=%s error=%s",
                _hash_email_for_key(email)[:8] + "...",
                str(e),
            )
            return result
    
    async def invalidate(self, email: str) -> LoginUserCacheResult:
        """
        Invalidate (delete) cached login user data.
        
        Call this when user data that affects login changes:
        - password change
        - status change
        - activation change
        - soft delete
        
        Args:
            email: Normalized email to invalidate
            
        Returns:
            LoginUserCacheResult with timing
        """
        start = time.perf_counter()
        result = LoginUserCacheResult(cache_hit=False, duration_ms=0)
        
        if not self._enabled:
            result.duration_ms = (time.perf_counter() - start) * 1000
            return result
        
        try:
            client = await self._get_redis_client()
            if not client:
                result.duration_ms = (time.perf_counter() - start) * 1000
                result.error = "redis_not_available"
                return result
            
            key = _build_cache_key(email)
            deleted = await client.delete(key)
            
            result.duration_ms = (time.perf_counter() - start) * 1000
            
            if deleted:
                logger.debug(
                    "login_user_cache_invalidated email_hash=%s duration_ms=%.2f",
                    _hash_email_for_key(email)[:8] + "...",
                    result.duration_ms,
                )
            
            return result
            
        except Exception as e:
            result.duration_ms = (time.perf_counter() - start) * 1000
            result.error = str(e)
            logger.debug(
                "login_user_cache_invalidate_failed email_hash=%s error=%s",
                _hash_email_for_key(email)[:8] + "...",
                str(e),
            )
            return result


def get_login_user_cache() -> LoginUserCache:
    """Get singleton login user cache."""
    return LoginUserCache.get_instance()


# ─────────────────────────────────────────────────────────────────────────────
# Invalidation helper for use in services
# ─────────────────────────────────────────────────────────────────────────────

async def invalidate_login_user_cache(email: str) -> None:
    """
    Helper to invalidate login user cache for an email.
    
    Call this from services when login-relevant data changes:
    - password change
    - user_status change
    - user_is_activated change
    - deleted_at change (soft delete)
    
    Best-effort: silently ignores errors.
    """
    if not email:
        return
    try:
        norm_email = email.strip().lower()
        cache = get_login_user_cache()
        await cache.invalidate(norm_email)
    except Exception:
        pass  # Best-effort, silent


__all__ = [
    "LoginUserCache",
    "LoginUserCacheData",
    "LoginUserCacheResult",
    "get_login_user_cache",
    "invalidate_login_user_cache",
    "LOGIN_USER_CACHE_TTL_SECONDS",
]
