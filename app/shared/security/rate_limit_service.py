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
         2026-01-10 - Reduced log verbosity for production (RATE_LIMIT_DEBUG flag)
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

# Environment flag to enable verbose rate limit debug logs (default: off in production)
RATE_LIMIT_DEBUG = os.getenv("RATE_LIMIT_DEBUG", "0").lower() in ("1", "true", "yes")


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

# LUA script for combined rate limiting (email + IP in 1 roundtrip)
# Returns: [email_count, email_ttl, ip_count, ip_ttl]
RATE_LIMIT_COMBINED_LUA_SCRIPT = """
local email_key = KEYS[1]
local ip_key = KEYS[2]
local email_window = tonumber(ARGV[1])
local ip_window = tonumber(ARGV[2])

local email_count = redis.call('INCR', email_key)
if email_count == 1 then
    redis.call('EXPIRE', email_key, email_window)
end
local email_ttl = redis.call('TTL', email_key)

local ip_count = redis.call('INCR', ip_key)
if ip_count == 1 then
    redis.call('EXPIRE', ip_key, ip_window)
end
local ip_ttl = redis.call('TTL', ip_key)

return {email_count, email_ttl, ip_count, ip_ttl}
"""

# LUA script for reset keys (best-effort, 1 roundtrip)
RATE_LIMIT_RESET_LUA_SCRIPT = """
redis.call('DEL', KEYS[1])
redis.call('DEL', KEYS[2])
return 1
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
class RateLimitDecision:
    """
    Result of combined rate limit check (email + IP in 1 roundtrip).
    
    Attributes:
        allowed: True if both email and IP are within limits
        blocked_by: "email", "ip", or None if allowed
        email_count: Current count for email
        ip_count: Current count for IP
        email_retry_after: Seconds until email limit resets
        ip_retry_after: Seconds until IP limit resets
        timings: Detailed timing breakdown for observability
    """
    allowed: bool
    blocked_by: Optional[str] = None
    email_count: int = 0
    ip_count: int = 0
    email_limit: int = 5
    ip_limit: int = 20
    email_retry_after: int = 0
    ip_retry_after: int = 0
    timings: Dict[str, float] = field(default_factory=dict)
    roundtrips: int = 1
    
    @property
    def retry_after(self) -> int:
        """Return the relevant retry_after based on what was blocked."""
        if self.blocked_by == "email":
            return self.email_retry_after
        elif self.blocked_by == "ip":
            return self.ip_retry_after
        return 0


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
        
        # Async Redis client (from canonical module, lazy initialized)
        self._async_client: Optional[Any] = None
        self._async_connected: Optional[bool] = None  # None = not tried, True/False = result
        self._lua_script_sha: Optional[str] = None
        self._lua_combined_sha: Optional[str] = None  # Combined email+IP check
        self._lua_reset_sha: Optional[str] = None      # Reset keys
        self._scripts_loaded: bool = False             # Flag to track if scripts are loaded
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
        
        # Log initialization once per process with PID
        pid = os.getpid()
        if self._redis_url:
            logger.info("RateLimitService: async Redis configured (lazy connect) pid=%d", pid)
        else:
            logger.info("RateLimitService: REDIS_URL not configured, using in-memory storage pid=%d", pid)
    
    @property
    def is_enabled(self) -> bool:
        return self._enabled
    
    @property
    def is_redis_connected(self) -> bool:
        return self._async_connected is True
    
    # ─────────────────────────────────────────────────────────────────────────
    # PUBLIC: Warmup method for startup
    # ─────────────────────────────────────────────────────────────────────────
    
    async def warmup(self) -> "RedisWarmupResult":
        """
        Public warmup method for startup.
        
        Performs:
        1. Connect to Redis (if not already connected)
        2. Execute PING
        3. Load LUA scripts
        
        Returns:
            RedisWarmupResult with ping_ok, scripts_loaded, duration_ms
            
        Note:
            Best-effort: NEVER raises exceptions.
        """
        from app.shared.security.redis_warmup import RedisWarmupResult
        
        start = time.perf_counter()
        result = RedisWarmupResult(success=False, duration_ms=0)
        
        if not self._redis_url:
            result.duration_ms = (time.perf_counter() - start) * 1000
            result.error = "REDIS_URL not configured"
            return result
        
        try:
            # Ensure connection (will also load scripts)
            connected = await self._ensure_async_connection()
            
            if not connected:
                result.duration_ms = (time.perf_counter() - start) * 1000
                result.error = "Connection failed"
                return result
            
            # Verify ping works
            try:
                await self._async_client.ping()
                result.ping_ok = True
            except Exception as e:
                result.duration_ms = (time.perf_counter() - start) * 1000
                result.error = f"PING failed: {str(e)}"
                return result
            
            # Count loaded scripts
            scripts_loaded = 0
            if self._lua_script_sha:
                scripts_loaded += 1
            if self._lua_combined_sha:
                scripts_loaded += 1
            if self._lua_reset_sha:
                scripts_loaded += 1
            
            result.scripts_loaded = scripts_loaded
            result.success = True
            result.duration_ms = (time.perf_counter() - start) * 1000
            
            return result
            
        except Exception as e:
            result.duration_ms = (time.perf_counter() - start) * 1000
            result.error = str(e)
            return result
    
    async def _ensure_async_connection(self) -> bool:
        """
        Lazy-connect to Redis async using canonical client.
        Returns True if connected, False otherwise.
        
        FAIL-SAFE: This method NEVER raises exceptions.
        Uses the canonical Redis client from app.shared.redis.
        
        Note: Lock is created lazily here (not in __init__) to avoid
        issues when singleton is created outside of an event loop.
        """
        if self._async_connected is not None:
            return self._async_connected
        
        if not self._redis_url:
            self._async_connected = False
            return False
        
        # Guardrail: verify we have a running loop before creating lock
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
                # Use canonical Redis client
                from app.shared.redis import get_async_redis_client
                
                self._async_client = await get_async_redis_client()
                
                if self._async_client is None:
                    logger.warning(
                        "RateLimitService: canonical Redis client unavailable, using in-memory fallback"
                    )
                    self._async_connected = False
                    return False
                
                # Load LUA scripts
                await self._ensure_scripts_loaded()
                
                self._async_connected = True
                logger.info(
                    "RateLimitService: using canonical Redis client, LUA scripts loaded pid=%d",
                    os.getpid()
                )
                return True
                
            except Exception as e:
                logger.warning(
                    "RateLimitService: async Redis connection failed, using in-memory fallback: %s",
                    str(e)
                )
                self._async_connected = False
                self._async_client = None
                return False
    
    async def _ensure_scripts_loaded(self) -> bool:
        """
        Load LUA scripts if not already loaded.
        
        Returns:
            True if all scripts are loaded, False otherwise.
        """
        if self._scripts_loaded:
            return True
        
        if self._async_client is None:
            return False
        
        try:
            self._lua_script_sha = await self._async_client.script_load(
                RATE_LIMIT_LUA_SCRIPT
            )
            self._lua_combined_sha = await self._async_client.script_load(
                RATE_LIMIT_COMBINED_LUA_SCRIPT
            )
            self._lua_reset_sha = await self._async_client.script_load(
                RATE_LIMIT_RESET_LUA_SCRIPT
            )
            self._scripts_loaded = True
            return True
        except Exception as e:
            logger.warning("RateLimitService: failed to load LUA scripts: %s", str(e))
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
    
    async def check_login_limits_combined(
        self,
        email: str,
        ip_address: str,
    ) -> RateLimitDecision:
        """
        Combined rate limit check for login: email + IP in 1 roundtrip.
        
        This is the preferred method for login endpoints as it:
        - Uses 1 Redis roundtrip instead of 2
        - Provides detailed timing breakdown for observability
        - Returns RateLimitDecision with all timing metadata
        
        Args:
            email: User email for lockout tracking
            ip_address: Client IP for rate limiting
            
        Returns:
            RateLimitDecision with allowed status and timing breakdown
        """
        start_total = time.perf_counter()
        timings: Dict[str, float] = {}
        
        if not self._enabled:
            return RateLimitDecision(
                allowed=True,
                email_count=0,
                ip_count=0,
                timings={"total_ms": 0, "redis_rtt_ms": 0},
                roundtrips=0,
            )
        
        # Get limits from defaults
        email_config = self.DEFAULT_LIMITS.get("auth:login:email", {"limit": 5, "window": 900})
        ip_config = self.DEFAULT_LIMITS.get("auth:login:ip", {"limit": 20, "window": 300})
        
        email_limit = email_config["limit"]
        email_window = email_config["window"]
        ip_limit = ip_config["limit"]
        ip_window = ip_config["window"]
        
        email_key = self._build_key("auth:login", "email", email)
        ip_key = self._build_key("auth:login", "ip", ip_address)
        
        # Try async Redis first
        redis_ok = await self._ensure_async_connection()
        
        if redis_ok:
            return await self._check_combined_redis_async(
                email_key, ip_key,
                email_limit, email_window,
                ip_limit, ip_window,
                start_total,
            )
        else:
            return self._check_combined_memory(
                email_key, ip_key,
                email_limit, email_window,
                ip_limit, ip_window,
                start_total,
            )
    
    async def _check_combined_redis_async(
        self,
        email_key: str,
        ip_key: str,
        email_limit: int,
        email_window: int,
        ip_limit: int,
        ip_window: int,
        start_total: float,
    ) -> RateLimitDecision:
        """
        Combined check using LUA script (1 roundtrip for both email + IP).
        """
        timings: Dict[str, float] = {}
        roundtrips = 1
        
        # Ensure combined LUA script SHA is loaded
        if not self._lua_combined_sha:
            self._lua_combined_sha = await self._async_client.script_load(
                RATE_LIMIT_COMBINED_LUA_SCRIPT
            )
            roundtrips = 2
        
        redis_start = time.perf_counter()
        try:
            # Execute combined LUA script
            result = await self._async_client.evalsha(
                self._lua_combined_sha,
                2,  # number of keys
                email_key,
                ip_key,
                email_window,
                ip_window,
            )
            
            timings["redis_rtt_ms"] = (time.perf_counter() - redis_start) * 1000
            
            email_count = int(result[0])
            email_ttl = int(result[1])
            ip_count = int(result[2])
            ip_ttl = int(result[3])
            
            # Handle edge case: TTL < 0 means key has no expiry
            if email_ttl < 0:
                email_ttl = email_window
            if ip_ttl < 0:
                ip_ttl = ip_window
            
            # Check limits
            email_allowed = email_count <= email_limit
            ip_allowed = ip_count <= ip_limit
            
            blocked_by = None
            if not email_allowed:
                blocked_by = "email"
            elif not ip_allowed:
                blocked_by = "ip"
            
            timings["total_ms"] = (time.perf_counter() - start_total) * 1000
            # NOTE: No invented breakdown (email_check_ms/ip_check_ms) - only real metrics
            
            decision = RateLimitDecision(
                allowed=email_allowed and ip_allowed,
                blocked_by=blocked_by,
                email_count=email_count,
                ip_count=ip_count,
                email_limit=email_limit,
                ip_limit=ip_limit,
                email_retry_after=email_ttl if not email_allowed else 0,
                ip_retry_after=ip_ttl if not ip_allowed else 0,
                timings=timings,
                roundtrips=roundtrips,
            )
            
            if blocked_by:
                logger.warning(
                    "rate_limit_exceeded_combined blocked_by=%s "
                    "email_count=%d/%d ip_count=%d/%d retry_after=%d",
                    blocked_by, email_count, email_limit, ip_count, ip_limit,
                    decision.retry_after
                )
            elif RATE_LIMIT_DEBUG and logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "rate_limit_combined_check email_count=%d/%d ip_count=%d/%d "
                    "redis_rtt_ms=%.2f roundtrips=%d",
                    email_count, email_limit, ip_count, ip_limit,
                    timings["redis_rtt_ms"], roundtrips
                )
            
            return decision
            
        except Exception as e:
            error_str = str(e).upper()
            if "NOSCRIPT" in error_str:
                # Script evicted, reload and retry
                logger.warning("rate_limit_combined_noscript - reloading LUA script")
                self._lua_combined_sha = await self._async_client.script_load(
                    RATE_LIMIT_COMBINED_LUA_SCRIPT
                )
                roundtrips = 3
                
                result = await self._async_client.evalsha(
                    self._lua_combined_sha,
                    2,
                    email_key,
                    ip_key,
                    email_window,
                    ip_window,
                )
                
                timings["redis_rtt_ms"] = (time.perf_counter() - redis_start) * 1000
                email_count = int(result[0])
                email_ttl = int(result[1])
                ip_count = int(result[2])
                ip_ttl = int(result[3])
                
                if email_ttl < 0:
                    email_ttl = email_window
                if ip_ttl < 0:
                    ip_ttl = ip_window
                
                email_allowed = email_count <= email_limit
                ip_allowed = ip_count <= ip_limit
                
                blocked_by = None
                if not email_allowed:
                    blocked_by = "email"
                elif not ip_allowed:
                    blocked_by = "ip"
                
                timings["total_ms"] = (time.perf_counter() - start_total) * 1000
                
                return RateLimitDecision(
                    allowed=email_allowed and ip_allowed,
                    blocked_by=blocked_by,
                    email_count=email_count,
                    ip_count=ip_count,
                    email_limit=email_limit,
                    ip_limit=ip_limit,
                    email_retry_after=email_ttl if not email_allowed else 0,
                    ip_retry_after=ip_ttl if not ip_allowed else 0,
                    timings=timings,
                    roundtrips=roundtrips,
                )
            
            # Fail-open on Redis errors
            timings["redis_rtt_ms"] = (time.perf_counter() - redis_start) * 1000
            timings["total_ms"] = (time.perf_counter() - start_total) * 1000
            logger.error(
                "rate_limit_combined_redis_error error=%s elapsed_ms=%.2f - falling back to allow",
                str(e), timings["total_ms"]
            )
            return RateLimitDecision(
                allowed=True,
                email_count=0,
                ip_count=0,
                timings=timings,
                roundtrips=roundtrips,
            )
    
    def _check_combined_memory(
        self,
        email_key: str,
        ip_key: str,
        email_limit: int,
        email_window: int,
        ip_limit: int,
        ip_window: int,
        start_total: float,
    ) -> RateLimitDecision:
        """
        Combined in-memory rate limit check (fallback when Redis unavailable).
        """
        timings: Dict[str, float] = {}
        now = time.time()
        
        with self._mem_lock:
            # Check/update email
            email_record = self._mem_storage.get(email_key)
            if email_record is None or email_record.is_expired(email_window):
                email_record = InMemoryRecord(count=1, window_start=now)
                self._mem_storage[email_key] = email_record
            else:
                email_record.count += 1
            
            # Check/update IP
            ip_record = self._mem_storage.get(ip_key)
            if ip_record is None or ip_record.is_expired(ip_window):
                ip_record = InMemoryRecord(count=1, window_start=now)
                self._mem_storage[ip_key] = ip_record
            else:
                ip_record.count += 1
        
        email_count = email_record.count
        ip_count = ip_record.count
        
        email_allowed = email_count <= email_limit
        ip_allowed = ip_count <= ip_limit
        
        blocked_by = None
        email_retry_after = 0
        ip_retry_after = 0
        
        if not email_allowed:
            blocked_by = "email"
            email_retry_after = int(email_window - (now - email_record.window_start))
        elif not ip_allowed:
            blocked_by = "ip"
            ip_retry_after = int(ip_window - (now - ip_record.window_start))
        
        timings["total_ms"] = (time.perf_counter() - start_total) * 1000
        timings["redis_rtt_ms"] = 0  # In-memory, no RTT
        
        return RateLimitDecision(
            allowed=email_allowed and ip_allowed,
            blocked_by=blocked_by,
            email_count=email_count,
            ip_count=ip_count,
            email_limit=email_limit,
            ip_limit=ip_limit,
            email_retry_after=max(0, email_retry_after),
            ip_retry_after=max(0, ip_retry_after),
            timings=timings,
            roundtrips=0,
        )
    
    async def reset_login_limits_async(
        self,
        email: str,
        ip_address: str,
    ) -> Dict[str, float]:
        """
        Reset login rate limit counters on successful login (1 roundtrip).
        
        Returns:
            Timing dict with reset_ms and roundtrips
        """
        start = time.perf_counter()
        timings: Dict[str, float] = {"roundtrips": 0}
        
        email_key = self._build_key("auth:login", "email", email)
        ip_key = self._build_key("auth:login", "ip", ip_address)
        
        redis_ok = await self._ensure_async_connection()
        
        if redis_ok:
            try:
                # Use LUA script for 1-roundtrip reset
                if not self._lua_reset_sha:
                    self._lua_reset_sha = await self._async_client.script_load(
                        RATE_LIMIT_RESET_LUA_SCRIPT
                    )
                    timings["roundtrips"] = 2
                else:
                    timings["roundtrips"] = 1
                
                await self._async_client.evalsha(
                    self._lua_reset_sha,
                    2,
                    email_key,
                    ip_key,
                )
            except Exception as e:
                error_str = str(e).upper()
                if "NOSCRIPT" in error_str:
                    self._lua_reset_sha = await self._async_client.script_load(
                        RATE_LIMIT_RESET_LUA_SCRIPT
                    )
                    await self._async_client.evalsha(
                        self._lua_reset_sha,
                        2,
                        email_key,
                        ip_key,
                    )
                    timings["roundtrips"] = 3
                else:
                    logger.warning("rate_limit_reset_combined_failed error=%s", str(e))
        else:
            with self._mem_lock:
                self._mem_storage.pop(email_key, None)
                self._mem_storage.pop(ip_key, None)
        
        timings["reset_ms"] = (time.perf_counter() - start) * 1000
        return timings

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
            
            # Only log debug details if RATE_LIMIT_DEBUG is explicitly enabled
            if RATE_LIMIT_DEBUG and logger.isEnabledFor(logging.DEBUG):
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


__all__ = ["RateLimitService", "RateLimitResult", "RateLimitDecision", "get_rate_limiter"]
