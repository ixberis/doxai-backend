# -*- coding: utf-8 -*-
"""
backend/app/shared/security/login_cache_warmup.py

Warmup del login cache en startup (best-effort).

NO consulta por emails reales.
Solo asegura que el cliente Redis esté conectado y pipelines funcionando.

Autor: DoxAI
Fecha: 2026-01-12
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class LoginCacheWarmupResult:
    """Resultado del warmup del login cache."""
    success: bool
    duration_ms: float
    redis_connected: bool = False
    pipeline_tested: bool = False
    error: Optional[str] = None


async def warmup_login_cache_async() -> LoginCacheWarmupResult:
    """
    Warmup del login cache en startup (best-effort).
    
    Operaciones:
    1. Asegurar conexión Redis (via RedisClientManager)
    2. SET/DEL clave dummy para verificar pipeline
    
    NO hace consultas a DB ni cachea usuarios reales.
    
    Returns:
        LoginCacheWarmupResult con timing y estado.
    """
    import os
    
    start = time.perf_counter()
    result = LoginCacheWarmupResult(
        success=False,
        duration_ms=0,
    )
    
    # Early exit if Redis is not configured (avoid connection timeout)
    redis_url = os.getenv("REDIS_URL", "").strip()
    if not redis_url:
        result.duration_ms = (time.perf_counter() - start) * 1000
        result.error = "redis_not_configured"
        logger.debug(
            "login_cache_warmup_skipped reason=%s duration_ms=%.2f",
            result.error,
            result.duration_ms,
        )
        return result
    
    try:
        # Get Redis client from canonical manager
        from app.shared.redis import get_async_redis_client
        
        client = await get_async_redis_client()
        if not client:
            result.duration_ms = (time.perf_counter() - start) * 1000
            result.error = "redis_client_not_available"
            logger.debug(
                "login_cache_warmup_skipped reason=%s duration_ms=%.2f",
                result.error,
                result.duration_ms,
            )
            return result
        
        result.redis_connected = True
        
        # Test pipeline with dummy SET/DEL
        dummy_key = "__login_cache_warmup_test__"
        dummy_value = "warmup_check"
        
        # SET with 1 second TTL
        await client.setex(dummy_key, 1, dummy_value)
        
        # GET to verify
        retrieved = await client.get(dummy_key)
        
        # DEL immediately
        await client.delete(dummy_key)
        
        if retrieved == dummy_value or retrieved == dummy_value.encode():
            result.pipeline_tested = True
        
        result.success = result.redis_connected and result.pipeline_tested
        result.duration_ms = (time.perf_counter() - start) * 1000
        
        logger.info(
            "login_cache_warmup_success duration_ms=%.2f redis=%s pipeline=%s",
            result.duration_ms,
            result.redis_connected,
            result.pipeline_tested,
        )
        
        return result
        
    except Exception as e:
        result.duration_ms = (time.perf_counter() - start) * 1000
        result.error = str(e)
        
        logger.warning(
            "login_cache_warmup_failed error=%s duration_ms=%.2f",
            result.error,
            result.duration_ms,
        )
        
        return result


__all__ = [
    "warmup_login_cache_async",
    "LoginCacheWarmupResult",
]
