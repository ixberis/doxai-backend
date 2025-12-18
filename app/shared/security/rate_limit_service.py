# -*- coding: utf-8 -*-
"""
backend/app/shared/security/rate_limit_service.py

Rate limiting service with Redis + in-memory fallback.
Provides atomic operations for rate limiting auth endpoints.

Author: DoxAI
Updated: 2025-12-18
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import threading
from dataclasses import dataclass, field
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

# Try to import redis
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    redis = None
    REDIS_AVAILABLE = False


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
    Rate limiting service with Redis-ready architecture.
    
    Features:
    - Redis as primary storage (if REDIS_URL configured)
    - In-memory fallback when Redis unavailable
    - Atomic operations for distributed safety
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
        """Reset singleton (for testing)."""
        with cls._lock:
            cls._instance = None
    
    def __init__(self):
        self._enabled = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
        self._redis_url = os.getenv("REDIS_URL")
        self._redis_client: Optional[Any] = None
        self._mem_storage: Dict[str, InMemoryRecord] = {}
        self._mem_lock = threading.Lock()
        
        # Initialize Redis if available
        if self._redis_url and REDIS_AVAILABLE:
            try:
                self._redis_client = redis.from_url(
                    self._redis_url,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                )
                # Test connection
                self._redis_client.ping()
                logger.info("RateLimitService: Redis connected successfully")
            except Exception as e:
                logger.warning(f"RateLimitService: Redis connection failed, using in-memory fallback: {e}")
                self._redis_client = None
        else:
            if not self._redis_url:
                logger.info("RateLimitService: REDIS_URL not configured, using in-memory storage")
            elif not REDIS_AVAILABLE:
                logger.warning("RateLimitService: redis package not installed, using in-memory storage")
    
    @property
    def is_enabled(self) -> bool:
        return self._enabled
    
    @property
    def is_redis_connected(self) -> bool:
        return self._redis_client is not None
    
    def _build_key(self, endpoint: str, key_type: str, identifier: str) -> str:
        """Build standardized rate limit key."""
        # Normalize identifier (lowercase email, etc.)
        normalized = identifier.lower().strip() if identifier else "unknown"
        return f"rl:{endpoint}:{key_type}:{normalized}"
    
    def check_and_consume(
        self,
        endpoint: str,
        key_type: str,
        identifier: str,
        limit: Optional[int] = None,
        window_sec: Optional[int] = None,
    ) -> RateLimitResult:
        """
        Check rate limit and consume one request if allowed.
        
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
        
        # Get default limits if not specified
        config_key = f"{endpoint}:{key_type}"
        defaults = self.DEFAULT_LIMITS.get(config_key, {"limit": 10, "window": 60})
        
        actual_limit = limit if limit is not None else defaults["limit"]
        actual_window = window_sec if window_sec is not None else defaults["window"]
        
        key = self._build_key(endpoint, key_type, identifier)
        
        if self._redis_client:
            return self._check_redis(key, actual_limit, actual_window)
        else:
            return self._check_memory(key, actual_limit, actual_window)
    
    def _check_redis(self, key: str, limit: int, window_sec: int) -> RateLimitResult:
        """Check rate limit using Redis with atomic operations."""
        try:
            pipe = self._redis_client.pipeline()
            
            # Use INCR + TTL for atomic rate limiting
            pipe.incr(key)
            pipe.ttl(key)
            results = pipe.execute()
            
            current_count = int(results[0])
            ttl = int(results[1])
            
            # Set expiry if TTL is missing or invalid:
            # -1 = key exists but no expiry set
            # -2 = key doesn't exist (shouldn't happen after INCR, but handle edge case)
            # <0 = any other invalid state
            if ttl < 0:
                self._redis_client.expire(key, window_sec)
                ttl = window_sec
            
            allowed = current_count <= limit
            remaining = max(0, limit - current_count)
            retry_after = ttl if not allowed else 0
            
            if not allowed:
                logger.warning(
                    f"Rate limit exceeded: key={key}, count={current_count}, limit={limit}"
                )
            
            return RateLimitResult(
                allowed=allowed,
                remaining=remaining,
                retry_after=retry_after,
                current_count=current_count,
                limit=limit,
            )
            
        except Exception as e:
            logger.error(f"Redis rate limit check failed, falling back to allow: {e}")
            # Fail open to not block users on Redis errors
            return RateLimitResult(
                allowed=True,
                remaining=limit,
                retry_after=0,
                current_count=0,
                limit=limit,
            )
    
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
                    f"Rate limit exceeded (in-memory): key={key}, count={current_count}, limit={limit}"
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
            logger.debug(f"Rate limiter cleaned up {len(expired_keys)} expired records")
    
    def reset_key(self, endpoint: str, key_type: str, identifier: str) -> None:
        """
        Reset rate limit counter for a specific key.
        Used after successful login to clear attempt counters.
        """
        key = self._build_key(endpoint, key_type, identifier)
        
        if self._redis_client:
            try:
                self._redis_client.delete(key)
            except Exception as e:
                logger.error(f"Failed to reset Redis key {key}: {e}")
        else:
            with self._mem_lock:
                self._mem_storage.pop(key, None)
    
    def get_attempt_count(self, endpoint: str, key_type: str, identifier: str) -> int:
        """Get current attempt count for an identifier (for backoff calculation)."""
        key = self._build_key(endpoint, key_type, identifier)
        
        if self._redis_client:
            try:
                count = self._redis_client.get(key)
                return int(count) if count else 0
            except Exception:
                return 0
        else:
            with self._mem_lock:
                record = self._mem_storage.get(key)
                if record and not record.is_expired(900):  # 15 min default
                    return record.count
                return 0


# Convenience function
def get_rate_limiter() -> RateLimitService:
    """Get the singleton rate limit service."""
    return RateLimitService.get_instance()


__all__ = ["RateLimitService", "RateLimitResult", "get_rate_limiter"]
