# -*- coding: utf-8 -*-
"""
backend/app/shared/security/rate_limit_service.py

Rate limiting service with async Redis + in-memory fallback.
Provides atomic operations for rate limiting auth endpoints.

Optimizations (2026-01-10):
- Redis async (redis.asyncio) to avoid blocking event loop
- LUA script for 1-roundtrip atomic operations (INCR + EXPIRE + TTL)
- Lazy connection initialization (no blocking ping in __init__)

Author: DoxAI
Updated: 2026-01-10 - Async Redis + LUA script optimization
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import logging
import os
import time
import threading
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Try to import redis.asyncio (redis-py >= 4.2.0)
try:
    import redis.asyncio as aioredis
    REDIS_ASYNC_AVAILABLE = True
except ImportError:
    aioredis = None
    REDIS_ASYNC_AVAILABLE = False


# LUA script for atomic rate limiting (1 roundtrip)
# Returns: [current_count, ttl_remaining]
RATE_LIMIT_LUA_SCRIPT = """
local key = KEYS[1]
local window = tonumber(ARGV[1])

local count = redis.call('INCR', key)
if count == 1 then
    redis.call('EXPIRE', key, window)
end
local ttl = redis.call('TTL', key)
return {count, ttl}
"""


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""
    allowed: bool
    remaining: int
    retry_after: int  # seconds until limit resets
    current_count: int
    limit: int


@dataclass  
class InMemoryRecord:
    """In-memory rate limit record with TTL."""
    count: int = 0
    window_start: float = field(default_factory=time.time)
    
    def is_expired(self, window_sec: int) -> bool:
        return time.time() - self.window_start >= window_sec


class RateLimitService:
    """
    Rate limiting service with async Redis + in-memory fallback.
    
    Features:
    - Async Redis as primary storage (non-blocking)
    - LUA script for 1-roundtrip atomic operations
    - Lazy connection (no blocking in __init__)
    - In-memory fallback when Redis unavailable
    - Configurable via RATE_LIMIT_ENABLED env var
    
    Key naming convention:
    - rl:auth:register:ip:{ip}
    - rl:auth:login:ip:{ip}
    - rl:auth:login:email:{email}
    - rl:auth:forgot:ip:{ip}
    - rl:auth:forgot:email:{email}
    """
    
    _instance: Optional["RateLimitService"] = None
    _lock = threading.Lock()
    
    # Default rate limit configurations
    DEFAULT_LIMITS = {
        "auth:register:ip": {"limit": 3, "window": 600},      # 3 per 10 min
        "auth:login:ip": {"limit": 20, "window": 300},        # 20 per 5 min
        "auth:login:email": {"limit": 5, "window": 900},      # 5 per 15 min (lockout)
        "auth:forgot:ip": {"limit": 3, "window": 900},        # 3 per 15 min
        "auth:forgot:email": {"limit": 3, "window": 3600},    # 3 per 60 min
        "auth:activation:ip": {"limit": 5, "window": 600},    # 5 per 10 min
    }
    
    @classmethod
    def get_instance(cls) -> "RateLimitService":
        """Get singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """
        Reset singleton (for testing).
        
        IMPORTANT: Does NOT use asyncio.get_event_loop().run_until_complete
        to avoid blocking or errors in Windows PowerShell / pytest.
        
        Best-effort client close:
        - If running loop exists: schedule close as task
        - If no loop: skip close (tests typically mock clients anyway)
        
        Compatible with different redis.asyncio versions:
        - Uses aclose() if available (redis-py >= 4.5.0)
        - Falls back to close() for older versions
        - Handles both sync and async close methods
        """
        with cls._lock:
            if cls._instance is not None:
                instance = cls._instance
                if instance._async_client is not None:
                    try:
                        loop = asyncio.get_running_loop()
                        # Find appropriate close method (aclose or close)
                        close_method = getattr(
                            instance._async_client, 'aclose', None
                        ) or getattr(
                            instance._async_client, 'close', None
                        )
                        if close_method is not None:
                            result = close_method()
                            # If it returns an awaitable, schedule as task
                            if inspect.isawaitable(result):
                                loop.create_task(result)
                            # else: sync close already executed, nothing to schedule
                    except RuntimeError:
                        # No running loop - just skip close
                        pass
            cls._instance = None
    
    # Class-level flag to log salt warning only once
    _salt_warning_logged: bool = False
    
    def __init__(self):
        self._enabled = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
        self._redis_url = os.getenv("REDIS_URL")
        
        # Async Redis client (lazy initialized)
        self._async_client: Optional[Any] = None
        self._async_connected: Optional[bool] = None  # None = not tried, True/False = result
        self._lua_script_sha: Optional[str] = None
        # Lock created lazily in _ensure_async_connection to avoid loop issues
        self._connect_lock: Optional[asyncio.Lock] = None
        
        # In-memory fallback
        self._mem_storage: Dict[str, InMemoryRecord] = {}
        self._mem_lock = threading.Lock()
        
        # Ephemeral salt for fallback (unique per process startup)
        self._ephemeral_salt: str = f"ephemeral-{os.getpid()}-{int(time.time())}"
        
        # Check salt configuration once at init
        self._log_salt = os.getenv("RATE_LIMIT_LOG_SALT")
        if not self._log_salt and not RateLimitService._salt_warning_logged:
            logger.warning(
                "RateLimitService: RATE_LIMIT_LOG_SALT not configured. "
                "Using ephemeral salt (PII hashes will vary per process restart)."
            )
            RateLimitService._salt_warning_logged = True
        
        # Log initialization
        if self._redis_url and REDIS_ASYNC_AVAILABLE:
            logger.info("RateLimitService: async Redis configured (lazy connect)")
        elif not self._redis_url:
            logger.info("RateLimitService: REDIS_URL not configured, using in-memory storage")
        elif not REDIS_ASYNC_AVAILABLE:
            logger.warning("RateLimitService: redis.asyncio not available, using in-memory storage")
    
    @property
    def is_enabled(self) -> bool:
        return self._enabled
    
    @property
    def is_redis_connected(self) -> bool:
        return self._async_connected is True
    
    async def _ensure_async_connection(self) -> bool:
        """
        Lazy-connect to Redis async. Thread-safe via asyncio.Lock.
        Returns True if connected, False otherwise.
        
        FAIL-SAFE: This method NEVER raises exceptions.
        If no running loop or any error occurs, returns False (fallback to in-memory).
        
        Note: Lock is created lazily here (not in __init__) to avoid
        issues when singleton is created outside of an event loop.
        """
        if self._async_connected is not None:
            return self._async_connected
        
        if not self._redis_url or not REDIS_ASYNC_AVAILABLE:
            self._async_connected = False
            return False
        
        # Guardrail: verify we have a running loop before creating lock
        # FAIL-SAFE: if no loop, return False instead of raising
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("RateLimitService: no running event loop, using in-memory fallback")
            self._async_connected = False
            return False
        
        # Create lock lazily when we have a running loop
        if self._connect_lock is None:
            self._connect_lock = asyncio.Lock()
        
        async with self._connect_lock:
            # Double-check after acquiring lock
            if self._async_connected is not None:
                return self._async_connected
            
            try:
                self._async_client = aioredis.from_url(
                    self._redis_url,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
                # Test connection
                await self._async_client.ping()
                
                # Register LUA script
                self._lua_script_sha = await self._async_client.script_load(
                    RATE_LIMIT_LUA_SCRIPT
                )
                
                self._async_connected = True
                logger.info("RateLimitService: async Redis connected, LUA script loaded")
                return True
                
            except Exception as e:
                logger.warning(
                    "RateLimitService: async Redis connection failed, using in-memory fallback: %s",
                    str(e)
                )
                self._async_connected = False
                self._async_client = None
                return False
    
    def _mask_key_for_log(self, key: str) -> str:
        """
        Mask PII in rate limit keys for safe logging.
        Returns a salted short hash instead of the full key.
        
        Uses RATE_LIMIT_LOG_SALT from environment (no hardcoded fallback).
        If not configured, uses ephemeral salt (PID + start time) to avoid
        predictable hashing while preserving log functionality.
        """
        salt = self._log_salt if self._log_salt else self._ephemeral_salt
        salted = f"{salt}:{key}"
        return f"key_hash={hashlib.sha256(salted.encode()).hexdigest()[:8]}"
    
    def _build_key(self, endpoint: str, key_type: str, identifier: str) -> str:
        """Build standardized rate limit key."""
        normalized = identifier.lower().strip() if identifier else "unknown"
        return f"rl:{endpoint}:{key_type}:{normalized}"
    
    # ─────────────────────────────────────────────────────────────────────────
    # ASYNC API (preferred for auth endpoints)
    # ─────────────────────────────────────────────────────────────────────────
    
    async def check_and_consume_async(
        self,
        endpoint: str,
        key_type: str,
        identifier: str,
        limit: Optional[int] = None,
        window_sec: Optional[int] = None,
    ) -> RateLimitResult:
        """
        Async rate limit check with 1-roundtrip LUA script.
        
        Args:
            endpoint: Endpoint identifier (e.g., "auth:login")
            key_type: Key type ("ip" or "email")
            identifier: The actual identifier (IP address or email)
            limit: Max requests in window (uses default if None)
            window_sec: Window duration in seconds (uses default if None)
            
        Returns:
            RateLimitResult with allowed status and metadata
        """
        if not self._enabled:
            return RateLimitResult(
                allowed=True,
                remaining=999,
                retry_after=0,
                current_count=0,
                limit=999,
            )
        
        # Get default limits
        config_key = f"{endpoint}:{key_type}"
        defaults = self.DEFAULT_LIMITS.get(config_key, {"limit": 10, "window": 60})
        actual_limit = limit if limit is not None else defaults["limit"]
        actual_window = window_sec if window_sec is not None else defaults["window"]
        
        key = self._build_key(endpoint, key_type, identifier)
        
        # Try async Redis first
        redis_ok = await self._ensure_async_connection()
        
        if redis_ok:
            return await self._check_redis_async(key, actual_limit, actual_window)
        else:
            return self._check_memory(key, actual_limit, actual_window)
    
    async def _check_redis_async(
        self, key: str, limit: int, window_sec: int
    ) -> RateLimitResult:
        """
        Check rate limit using async Redis with LUA script (EVALSHA).
        
        Roundtrip counting:
        - Normal steady-state: 1 roundtrip (EVALSHA)
        - Cold start (no SHA): 2 roundtrips (SCRIPT_LOAD + EVALSHA)
        - NOSCRIPT recovery: 3 roundtrips (failed EVALSHA + SCRIPT_LOAD + EVALSHA)
        
        FAIL-OPEN: On any Redis error, allows the request through.
        """
        start = time.perf_counter()
        base_roundtrips = 0
        
        # Ensure LUA script SHA is loaded (defensive: should be set in _ensure_async_connection)
        if not self._lua_script_sha:
            self._lua_script_sha = await self._async_client.script_load(
                RATE_LIMIT_LUA_SCRIPT
            )
            base_roundtrips = 1  # SCRIPT_LOAD counts as 1 roundtrip
        
        try:
            result, helper_roundtrips = await self._execute_lua_with_noscript_retry(key, window_sec)
            
            # Total roundtrips = base (if we did SCRIPT_LOAD) + helper roundtrips
            total_roundtrips = base_roundtrips + helper_roundtrips
            
            current_count = int(result[0])
            ttl = int(result[1])
            
            # Handle edge case: TTL < 0 means key has no expiry
            if ttl < 0:
                ttl = window_sec
            
            allowed = current_count <= limit
            remaining = max(0, limit - current_count)
            retry_after = ttl if not allowed else 0
            
            elapsed_ms = (time.perf_counter() - start) * 1000
            
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "rate_limit_debug op=check %s redis_ms=%.2f roundtrips=%d "
                    "current_count=%d ttl=%d allowed=%s",
                    self._mask_key_for_log(key), elapsed_ms, total_roundtrips, current_count, ttl, allowed
                )
            
            if not allowed:
                logger.warning(
                    "rate_limit_exceeded %s count=%d limit=%d retry_after=%d",
                    self._mask_key_for_log(key), current_count, limit, retry_after
                )
            
            return RateLimitResult(
                allowed=allowed,
                remaining=remaining,
                retry_after=retry_after,
                current_count=current_count,
                limit=limit,
            )
            
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "rate_limit_redis_error %s error=%s elapsed_ms=%.2f base_roundtrips=%d - falling back to allow",
                self._mask_key_for_log(key), str(e), elapsed_ms, base_roundtrips
            )
            # Fail open to not block users on Redis errors
            return RateLimitResult(
                allowed=True,
                remaining=limit,
                retry_after=0,
                current_count=0,
                limit=limit,
            )
    
    async def _execute_lua_with_noscript_retry(
        self, key: str, window_sec: int
    ) -> tuple[list, int]:
        """
        Execute LUA script via EVALSHA with automatic NOSCRIPT recovery.
        
        Flow:
        1. Try EVALSHA (1 roundtrip)
        2. If NOSCRIPT: SCRIPT_LOAD (1 roundtrip) + EVALSHA again (1 roundtrip) = 3 total
        
        Returns:
            Tuple of (result_list, roundtrips_count)
        """
        roundtrips = 0
        
        try:
            roundtrips = 1
            result = await self._async_client.evalsha(
                self._lua_script_sha,
                1,  # number of keys
                key,
                window_sec,
            )
            return result, roundtrips
            
        except Exception as e:
            error_str = str(e).upper()
            if "NOSCRIPT" in error_str:
                # Script was evicted from Redis cache, reload and retry
                logger.warning("rate_limit_noscript_detected - reloading LUA script")
                
                roundtrips = 2  # SCRIPT_LOAD
                self._lua_script_sha = await self._async_client.script_load(
                    RATE_LIMIT_LUA_SCRIPT
                )
                
                roundtrips = 3  # Second EVALSHA
                result = await self._async_client.evalsha(
                    self._lua_script_sha,
                    1,
                    key,
                    window_sec,
                )
                return result, roundtrips
            raise
    
    async def get_attempt_count_async(
        self, endpoint: str, key_type: str, identifier: str
    ) -> int:
        """Async get current attempt count (for backoff calculation)."""
        key = self._build_key(endpoint, key_type, identifier)
        
        redis_ok = await self._ensure_async_connection()
        
        if redis_ok:
            try:
                count = await self._async_client.get(key)
                return int(count) if count else 0
            except Exception:
                return 0
        else:
            with self._mem_lock:
                record = self._mem_storage.get(key)
                if record and not record.is_expired(900):
                    return record.count
                return 0
    
    async def reset_key_async(
        self, endpoint: str, key_type: str, identifier: str
    ) -> None:
        """Async reset rate limit counter for a specific key."""
        key = self._build_key(endpoint, key_type, identifier)
        
        redis_ok = await self._ensure_async_connection()
        
        if redis_ok:
            try:
                await self._async_client.delete(key)
            except Exception as e:
                logger.error("rate_limit_reset_failed key=%s error=%s", key, str(e))
        else:
            with self._mem_lock:
                self._mem_storage.pop(key, None)
    
    # ─────────────────────────────────────────────────────────────────────────
    # SYNC API (backward compatibility - wraps async or uses in-memory)
    # ─────────────────────────────────────────────────────────────────────────
    
    def check_and_consume(
        self,
        endpoint: str,
        key_type: str,
        identifier: str,
        limit: Optional[int] = None,
        window_sec: Optional[int] = None,
    ) -> RateLimitResult:
        """
        Sync rate limit check (for backward compatibility).
        
        WARNING: This uses in-memory storage only to avoid blocking event loop.
        For async endpoints, use check_and_consume_async() instead.
        """
        if not self._enabled:
            return RateLimitResult(
                allowed=True,
                remaining=999,
                retry_after=0,
                current_count=0,
                limit=999,
            )
        
        config_key = f"{endpoint}:{key_type}"
        defaults = self.DEFAULT_LIMITS.get(config_key, {"limit": 10, "window": 60})
        actual_limit = limit if limit is not None else defaults["limit"]
        actual_window = window_sec if window_sec is not None else defaults["window"]
        
        key = self._build_key(endpoint, key_type, identifier)
        
        # Sync API always uses in-memory to avoid blocking
        return self._check_memory(key, actual_limit, actual_window)
    
    def _check_memory(self, key: str, limit: int, window_sec: int) -> RateLimitResult:
        """Check rate limit using in-memory storage."""
        now = time.time()
        
        with self._mem_lock:
            # Clean up expired records periodically
            if len(self._mem_storage) > 10000:
                self._cleanup_expired(window_sec)
            
            record = self._mem_storage.get(key)
            
            if record is None or record.is_expired(window_sec):
                # Start new window
                record = InMemoryRecord(count=1, window_start=now)
                self._mem_storage[key] = record
                
                return RateLimitResult(
                    allowed=True,
                    remaining=limit - 1,
                    retry_after=0,
                    current_count=1,
                    limit=limit,
                )
            
            # Increment counter
            record.count += 1
            current_count = record.count
            
            allowed = current_count <= limit
            remaining = max(0, limit - current_count)
            retry_after = int(window_sec - (now - record.window_start)) if not allowed else 0
            
            if not allowed:
                logger.warning(
                    "rate_limit_exceeded_inmemory key=%s count=%d limit=%d",
                    key, current_count, limit
                )
            
            return RateLimitResult(
                allowed=allowed,
                remaining=remaining,
                retry_after=max(0, retry_after),
                current_count=current_count,
                limit=limit,
            )
    
    def _cleanup_expired(self, default_window: int) -> None:
        """Remove expired records from memory (called with lock held)."""
        now = time.time()
        expired_keys = [
            k for k, v in self._mem_storage.items()
            if v.is_expired(default_window)
        ]
        for k in expired_keys:
            del self._mem_storage[k]
        
        if expired_keys:
            logger.debug("rate_limiter_cleanup count=%d", len(expired_keys))
    
    def reset_key(self, endpoint: str, key_type: str, identifier: str) -> None:
        """
        Sync reset rate limit counter (backward compatibility).
        Only resets in-memory storage.
        """
        key = self._build_key(endpoint, key_type, identifier)
        with self._mem_lock:
            self._mem_storage.pop(key, None)
    
    def get_attempt_count(self, endpoint: str, key_type: str, identifier: str) -> int:
        """Sync get attempt count (in-memory only)."""
        key = self._build_key(endpoint, key_type, identifier)
        with self._mem_lock:
            record = self._mem_storage.get(key)
            if record and not record.is_expired(900):
                return record.count
            return 0


# Convenience function
def get_rate_limiter() -> RateLimitService:
    """Get the singleton rate limit service."""
    return RateLimitService.get_instance()


__all__ = ["RateLimitService", "RateLimitResult", "get_rate_limiter"]
