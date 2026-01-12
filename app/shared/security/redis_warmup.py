# -*- coding: utf-8 -*-
"""
backend/app/shared/security/redis_warmup.py

Redis warmup durante startup para reducir latencia del primer login.
Ejecuta PING + carga de scripts LUA de rate limiting.

Best-effort: si Redis falla, NO rompe el backend (solo log warning).

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
class RedisWarmupResult:
    """Resultado del warmup de Redis."""
    success: bool
    duration_ms: float
    ping_ok: bool = False
    scripts_loaded: int = 0
    error: Optional[str] = None


# Import at module level for proper patching in tests
from app.shared.security.rate_limit_service import get_rate_limiter


async def warmup_redis_async() -> RedisWarmupResult:
    """
    Ejecuta warmup de Redis al arranque del backend.
    
    Llama al método público warmup() del RateLimitService.
    NO lee REDIS_URL directamente - delega todo al rate_limiter.warmup().
    
    Best-effort: si falla, retorna RedisWarmupResult con success=False
    pero NO levanta excepción.
    
    Returns:
        RedisWarmupResult con detalles del warmup
    """
    logger.info("redis_warmup_started")
    
    try:
        rate_limiter = get_rate_limiter()
        
        # Use public warmup() method - no internals access
        result = await rate_limiter.warmup()
        
        if result.success:
            logger.info(
                "redis_warmup_success ping_ok=%s scripts_loaded=%d duration_ms=%.2f",
                result.ping_ok,
                result.scripts_loaded,
                result.duration_ms,
            )
        else:
            logger.warning(
                "redis_warmup_failed error=%s duration_ms=%.2f",
                result.error,
                result.duration_ms,
            )
        
        return result
        
    except Exception as e:
        result = RedisWarmupResult(
            success=False,
            duration_ms=0,
            error=str(e),
        )
        logger.warning(
            "redis_warmup_failed error=%s duration_ms=%.2f",
            str(e),
            result.duration_ms,
        )
        return result


__all__ = ["warmup_redis_async", "RedisWarmupResult"]
