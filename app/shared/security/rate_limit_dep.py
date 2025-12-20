# -*- coding: utf-8 -*-
"""
backend/app/shared/security/rate_limit_dep.py

FastAPI dependencies for rate limiting.
Provides configurable rate limiting per endpoint.

Author: DoxAI
Updated: 2025-12-18
"""
# Note: NOT using 'from __future__ import annotations' to ensure FastAPI
# can properly resolve Request type annotation for dependency injection

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
    """Create a standardized 429 response with explicit UTF-8 charset."""
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": message or "Demasiadas solicitudes. Intente de nuevo más tarde.",
            "retry_after": retry_after,
            "error_code": "rate_limit_exceeded",
        },
        headers={"Retry-After": str(retry_after)},
        media_type="application/json; charset=utf-8",
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
        
        # For email-based rate limiting (extracts from JSON body):
        @router.post("/activation/resend")
        async def resend(
            request: Request,
            _: None = Depends(RateLimitDep(endpoint="auth:resend", key_type="email"))
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
        body_field: Optional[str] = None,
    ):
        """
        Initialize rate limit dependency.
        
        Args:
            endpoint: Endpoint identifier (e.g., "auth:register")
            key_type: Key type ("ip" or "email")
            limit: Max requests in window (uses service default if None)
            window_sec: Window duration in seconds (uses service default if None)
            identifier_extractor: Optional function to extract identifier from request
            body_field: Field name to extract from JSON body (e.g., "email")
                       If key_type="email" and no extractor provided, defaults to "email"
        """
        self.endpoint = endpoint
        self.key_type = key_type
        self.limit = limit
        self.window_sec = window_sec
        self.identifier_extractor = identifier_extractor
        self.body_field = body_field
    
    async def __call__(self, request: Request) -> RateLimitResult:
        """Execute rate limit check."""
        limiter = get_rate_limiter()
        
        # Extract identifier
        identifier = await self._extract_identifier(request)
        
        # Skip rate limiting if we couldn't extract identifier for email
        if identifier == "unknown" and self.key_type == "email":
            # Can't rate limit by email if we don't have one
            # Return a dummy result that allows the request
            return RateLimitResult(
                allowed=True,
                current_count=0,
                limit=self.limit or 0,
                retry_after=0,
            )
        
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
    
    async def _extract_identifier(self, request: Request) -> str:
        """Extract identifier from request based on key_type."""
        if self.identifier_extractor:
            # Support both sync and async extractors
            import inspect
            result = self.identifier_extractor(request)
            if inspect.isawaitable(result):
                return await result
            return result
        
        if self.key_type == "ip":
            return get_client_ip(request)
        
        if self.key_type == "email":
            # Extract email from JSON body using Starlette's caching
            field = self.body_field or "email"
            try:
                body = await request.json()
                email = (body.get(field) or "").strip().lower()
                if email:
                    return email
                logger.debug(
                    f"Rate limit email extraction: field '{field}' empty or missing"
                )
                return "unknown"
            except Exception as e:
                logger.debug(
                    f"Rate limit email extraction failed: {type(e).__name__}"
                )
                return "unknown"
        
        return "unknown"


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
