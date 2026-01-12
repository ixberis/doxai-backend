# -*- coding: utf-8 -*-
"""
backend/app/shared/redis/client.py

Canonical async Redis client singleton for DoxAI.
Used by RateLimitService, AuthContextCache, HttpMetricsStore.

Features:
- Lazy connection initialization (no blocking in import)
- Single shared client across all consumers
- Best-effort: returns None if Redis not available
- Thread-safe singleton via asyncio.Lock

Autor: DoxAI
Fecha: 2026-01-12
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Try to import redis.asyncio (redis-py >= 4.2.0)
try:
    import redis.asyncio as aioredis
    REDIS_ASYNC_AVAILABLE = True
except ImportError:
    aioredis = None  # type: ignore
    REDIS_ASYNC_AVAILABLE = False


class RedisClientManager:
    """
    Manages a single shared async Redis client.
    
    Thread-safe singleton with lazy initialization.
    Best-effort: if Redis unavailable, returns None (fail-open).
    """
    
    _instance: Optional["RedisClientManager"] = None
    
    @classmethod
    def get_instance(cls) -> "RedisClientManager":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """
        Reset singleton (for testing).
        
        IMPORTANT: Does NOT close the client - just resets the instance.
        Use reset_instance_async() for proper cleanup with await.
        """
        cls._instance = None
    
    @classmethod
    async def reset_instance_async(cls) -> None:
        """
        Reset singleton with proper async cleanup.
        
        Use this in tests for proper cleanup.
        """
        if cls._instance is not None:
            await cls._instance.close()
        cls._instance = None
    
    def __init__(self):
        self._redis_url = os.getenv("REDIS_URL")
        self._client: Optional[Any] = None
        self._connected: Optional[bool] = None  # None = not tried
        self._connect_lock: Optional[asyncio.Lock] = None
        
        pid = os.getpid()
        if self._redis_url and REDIS_ASYNC_AVAILABLE:
            logger.debug("RedisClientManager: configured (lazy connect) pid=%d", pid)
        elif not self._redis_url:
            logger.debug("RedisClientManager: REDIS_URL not configured pid=%d", pid)
        elif not REDIS_ASYNC_AVAILABLE:
            logger.warning("RedisClientManager: redis.asyncio not available pid=%d", pid)
    
    @property
    def is_configured(self) -> bool:
        """True if Redis URL is configured and redis.asyncio is available."""
        return bool(self._redis_url) and REDIS_ASYNC_AVAILABLE
    
    @property
    def is_connected(self) -> bool:
        """True if successfully connected to Redis."""
        return self._connected is True
    
    async def get_client(self) -> Optional[Any]:
        """
        Get the async Redis client (lazy connect).
        
        Returns:
            Redis client or None if not available/failed.
            
        Note:
            NEVER raises exceptions - fail-open design.
        """
        if self._connected is not None:
            return self._client if self._connected else None
        
        if not self.is_configured:
            self._connected = False
            return None
        
        # Guardrail: verify we have a running loop
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("RedisClientManager: no running event loop")
            self._connected = False
            return None
        
        # Create lock lazily
        if self._connect_lock is None:
            self._connect_lock = asyncio.Lock()
        
        async with self._connect_lock:
            # Double-check after lock
            if self._connected is not None:
                return self._client if self._connected else None
            
            try:
                self._client = aioredis.from_url(
                    self._redis_url,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
                # Test connection
                await self._client.ping()
                
                self._connected = True
                logger.info(
                    "RedisClientManager: connected pid=%d",
                    os.getpid(),
                )
                return self._client
                
            except Exception as e:
                logger.warning(
                    "RedisClientManager: connection failed: %s",
                    str(e),
                )
                self._connected = False
                self._client = None
                return None
    
    async def ping(self) -> bool:
        """
        Execute PING command.
        
        Returns:
            True if PING successful, False otherwise.
        """
        client = await self.get_client()
        if not client:
            return False
        
        try:
            await client.ping()
            return True
        except Exception as e:
            logger.warning("RedisClientManager: ping failed: %s", str(e))
            return False
    
    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client is not None:
            try:
                close_method = getattr(self._client, 'aclose', None) or getattr(self._client, 'close', None)
                if close_method:
                    result = close_method()
                    if inspect.isawaitable(result):
                        await result
            except Exception as e:
                logger.warning("RedisClientManager: close error: %s", str(e))
            finally:
                self._client = None
                self._connected = None


async def get_async_redis_client() -> Optional[Any]:
    """
    Get the canonical async Redis client.
    
    Returns:
        Redis client or None if not available.
    """
    return await RedisClientManager.get_instance().get_client()


async def close_async_redis_client() -> None:
    """Close the Redis client connection."""
    await RedisClientManager.get_instance().close()


__all__ = [
    "get_async_redis_client",
    "close_async_redis_client",
    "RedisClientManager",
    "REDIS_ASYNC_AVAILABLE",
]
