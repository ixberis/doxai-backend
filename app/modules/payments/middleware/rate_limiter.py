
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/middleware/rate_limiter.py

Rate limiter para webhooks de pagos (FASE 3).

Implementa ventana deslizante en memoria con límite configurable por IP.

Autor: Ixchel Beristain
Fecha: 2025-12-13
"""

from __future__ import annotations

import os
import time
import logging
from collections import defaultdict
from typing import Dict, List, Tuple

from fastapi import Request, HTTPException, status

logger = logging.getLogger(__name__)

# Configuración por ENV
RATE_LIMIT_REQUESTS = int(os.getenv("WEBHOOK_RATE_LIMIT_REQUESTS", "10"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("WEBHOOK_RATE_LIMIT_WINDOW", "1"))
RATE_LIMIT_ENABLED = os.getenv("WEBHOOK_RATE_LIMIT_ENABLED", "true").lower() == "true"
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")


class SlidingWindowRateLimiter:
    """
    Rate limiter con ventana deslizante en memoria.
    
    Thread-safe para uso con FastAPI async.
    """
    
    def __init__(
        self,
        max_requests: int = RATE_LIMIT_REQUESTS,
        window_seconds: int = RATE_LIMIT_WINDOW_SECONDS,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # Dict[ip_address] -> List[timestamp]
        self._requests: Dict[str, List[float]] = defaultdict(list)
    
    def _cleanup_old_requests(self, ip: str, current_time: float) -> None:
        """Elimina requests fuera de la ventana."""
        cutoff = current_time - self.window_seconds
        self._requests[ip] = [
            ts for ts in self._requests[ip]
            if ts > cutoff
        ]
    
    def is_allowed(self, ip: str) -> Tuple[bool, int]:
        """
        Verifica si una IP puede hacer una request.
        
        Returns:
            Tuple[is_allowed, remaining_requests]
        """
        current_time = time.time()
        self._cleanup_old_requests(ip, current_time)
        
        current_count = len(self._requests[ip])
        
        if current_count >= self.max_requests:
            return False, 0
        
        # Registrar esta request
        self._requests[ip].append(current_time)
        remaining = self.max_requests - current_count - 1
        
        return True, remaining
    
    def get_retry_after(self, ip: str) -> int:
        """Calcula segundos hasta que la IP pueda volver a hacer requests."""
        if not self._requests[ip]:
            return 0
        
        oldest_request = min(self._requests[ip])
        retry_after = int(oldest_request + self.window_seconds - time.time()) + 1
        return max(1, retry_after)
    
    def reset(self) -> None:
        """Limpia todos los registros (útil para tests)."""
        self._requests.clear()


# Instancia global del rate limiter
_webhook_rate_limiter: SlidingWindowRateLimiter | None = None


def get_webhook_rate_limiter() -> SlidingWindowRateLimiter:
    """Obtiene la instancia global del rate limiter."""
    global _webhook_rate_limiter
    if _webhook_rate_limiter is None:
        _webhook_rate_limiter = SlidingWindowRateLimiter()
    return _webhook_rate_limiter


def reset_rate_limiter() -> None:
    """Resetea el rate limiter (útil para tests)."""
    global _webhook_rate_limiter
    if _webhook_rate_limiter:
        _webhook_rate_limiter.reset()


def _get_client_ip(request: Request) -> str:
    """Extrae la IP del cliente de la request."""
    # Verificar headers de proxy
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # Tomar la primera IP (cliente original)
        return forwarded.split(",")[0].strip()
    
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip
    
    # Fallback al client host
    if request.client:
        return request.client.host
    
    return "unknown"


async def check_webhook_rate_limit(request: Request) -> None:
    """
    Dependencia FastAPI para verificar rate limit en webhooks.
    
    Uso en rutas:
        @router.post("/webhook", dependencies=[Depends(check_webhook_rate_limit)])
    
    Raises:
        HTTPException 429 si se excede el límite.
    """
    # Desactivar en development si no está explícitamente habilitado
    if ENVIRONMENT == "development" and not RATE_LIMIT_ENABLED:
        return
    
    # Si está deshabilitado globalmente
    if not RATE_LIMIT_ENABLED:
        return
    
    client_ip = _get_client_ip(request)
    limiter = get_webhook_rate_limiter()
    
    is_allowed, remaining = limiter.is_allowed(client_ip)
    
    if not is_allowed:
        retry_after = limiter.get_retry_after(client_ip)
        logger.warning(
            f"Rate limit exceeded for IP {client_ip}. "
            f"Retry after {retry_after}s"
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Too many requests. Retry after {retry_after} seconds.",
                "retry_after_seconds": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )


__all__ = [
    "SlidingWindowRateLimiter",
    "get_webhook_rate_limiter",
    "reset_rate_limiter",
    "check_webhook_rate_limit",
    "RATE_LIMIT_REQUESTS",
    "RATE_LIMIT_WINDOW_SECONDS",
    "RATE_LIMIT_ENABLED",
]

# Fin del archivo backend/app/modules/payments/middleware/rate_limiter.py
