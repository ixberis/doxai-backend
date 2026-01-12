# -*- coding: utf-8 -*-
"""
backend/app/shared/redis/__init__.py

Redis client module for DoxAI.
Provides canonical async Redis client singleton.
"""

from .client import (
    get_async_redis_client,
    close_async_redis_client,
    RedisClientManager,
    REDIS_ASYNC_AVAILABLE,
)

__all__ = [
    "get_async_redis_client",
    "close_async_redis_client",
    "RedisClientManager",
    "REDIS_ASYNC_AVAILABLE",
]
