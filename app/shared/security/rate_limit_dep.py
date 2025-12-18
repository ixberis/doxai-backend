# -*- coding: utf-8 -*-
"""
backend/app/shared/security/rate_limit_dep.py

FastAPI dependencies for rate limiting.
Provides configurable rate limiting per endpoint.

Author: DoxAI
Updated: 2025-12-18
"""
from __future__ import annotations

import logging
from typing import Optional, Callable
from functools import wraps

from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse

from app.shared.security.rate_limit_service import get_rate_limiter, RateLimitResult
from app.shared.http_utils.request_meta import get_client_ip

logger = logging.getLogger(__name__)


class RateLimitExceeded(HTTPException):
    """Exception raised when rate limit is exceeded."""
    
    def __init__(self, retry_after: int, detail: Optional[str] = None):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail or "Demasiadas solicitudes. Intente de nuevo más tarde.",
            headers={"Retry-After": str(retry_after)},
        )
        self.retry_after = retry_after


def rate_limit_response(retry_after: int, message: Optional[str] = None) -> JSONResponse:
    """Create a standardized 429 response."""
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": message or "Demasiadas solicitudes. Intente de nuevo más tarde.",
            "retry_after": retry_after,
            "error_code": "rate_limit_exceeded",
        },
        headers={"Retry-After": str(retry_after)},
    )


class RateLimitDep:
    """
    FastAPI dependency for rate limiting.
    
    Usage:
        @router.post("/register")
        async def register(
            request: Request,
            _: None = Depends(RateLimitDep(endpoint="auth:register", key_type="ip"))
        ):
            ...
    """
    
    def __init__(
        self,
        endpoint: str,
        key_type: str = "ip",
        limit: Optional[int] = None,
        window_sec: Optional[int] = None,
        identifier_extractor: Optional[Callable[[Request], str]] = None,
    ):
        """
        Initialize rate limit dependency.
        
        Args:
            endpoint: Endpoint identifier (e.g., "auth:register")
            key_type: Key type ("ip" or "email")
            limit: Max requests in window (uses service default if None)
            window_sec: Window duration in seconds (uses service default if None)
            identifier_extractor: Optional function to extract identifier from request
        """
        self.endpoint = endpoint
        self.key_type = key_type
        self.limit = limit
        self.window_sec = window_sec
        self.identifier_extractor = identifier_extractor
    
    async def __call__(self, request: Request) -> RateLimitResult:
        """Execute rate limit check."""
        limiter = get_rate_limiter()
        
        # Extract identifier
        if self.identifier_extractor:
            identifier = self.identifier_extractor(request)
        elif self.key_type == "ip":
            identifier = get_client_ip(request)
        else:
            # For email, caller must provide extractor or handle separately
            identifier = "unknown"
        
        result = limiter.check_and_consume(
            endpoint=self.endpoint,
            key_type=self.key_type,
            identifier=identifier,
            limit=self.limit,
            window_sec=self.window_sec,
        )
        
        if not result.allowed:
            logger.warning(
                f"Rate limit exceeded: endpoint={self.endpoint}, "
                f"key_type={self.key_type}, identifier={_mask_identifier(identifier, self.key_type)}, "
                f"count={result.current_count}, limit={result.limit}"
            )
            raise RateLimitExceeded(
                retry_after=result.retry_after,
                detail=f"Demasiadas solicitudes. Intente de nuevo en {result.retry_after} segundos.",
            )
        
        return result


def check_rate_limit(
    request: Request,
    endpoint: str,
    key_type: str = "ip",
    identifier: Optional[str] = None,
    limit: Optional[int] = None,
    window_sec: Optional[int] = None,
) -> RateLimitResult:
    """
    Functional rate limit check for use within route handlers.
    
    Args:
        request: FastAPI request
        endpoint: Endpoint identifier
        key_type: "ip" or "email"
        identifier: Optional explicit identifier (defaults to client IP)
        limit: Optional limit override
        window_sec: Optional window override
        
    Returns:
        RateLimitResult
        
    Raises:
        RateLimitExceeded: If rate limit exceeded
    """
    limiter = get_rate_limiter()
    
    if identifier is None:
        identifier = get_client_ip(request) if key_type == "ip" else "unknown"
    
    result = limiter.check_and_consume(
        endpoint=endpoint,
        key_type=key_type,
        identifier=identifier,
        limit=limit,
        window_sec=window_sec,
    )
    
    if not result.allowed:
        logger.warning(
            f"Rate limit exceeded: endpoint={endpoint}, "
            f"key_type={key_type}, identifier={_mask_identifier(identifier, key_type)}, "
            f"count={result.current_count}, limit={result.limit}"
        )
        raise RateLimitExceeded(
            retry_after=result.retry_after,
            detail=f"Demasiadas solicitudes. Intente de nuevo en {result.retry_after} segundos.",
        )
    
    return result


def _mask_identifier(identifier: str, key_type: str) -> str:
    """Mask identifier for logging (privacy)."""
    if not identifier or identifier == "unknown":
        return identifier
    
    if key_type == "email":
        # Mask email: jo***@example.com
        if "@" in identifier:
            local, domain = identifier.split("@", 1)
            if len(local) > 2:
                return f"{local[:2]}***@{domain}"
            return f"***@{domain}"
        return "***"
    
    if key_type == "ip":
        # Mask IP: 192.168.***
        parts = identifier.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.***.***"
        # IPv6 or unknown format
        if len(identifier) > 8:
            return f"{identifier[:8]}***"
    
    return identifier[:4] + "***" if len(identifier) > 4 else "***"


__all__ = [
    "RateLimitDep",
    "RateLimitExceeded", 
    "check_rate_limit",
    "rate_limit_response",
]
