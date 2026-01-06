# -*- coding: utf-8 -*-
"""
backend/app/shared/observability/http_metrics_middleware.py

Middleware FastAPI para contar errores HTTP (4xx/5xx).

Solo cuenta rutas de Auth por defecto.
Usa HttpMetricsStore para flush periódico a DB.

Autor: Sistema
Fecha: 2026-01-06
"""
from __future__ import annotations

import logging
import re
from typing import Callable, List, Optional, Pattern

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .http_metrics_store import get_http_metrics_store

logger = logging.getLogger(__name__)

# Default patterns for Auth routes
AUTH_ROUTE_PATTERNS = [
    re.compile(r"^/api/auth/"),
    re.compile(r"^/_internal/auth/"),
    re.compile(r"^/auth/"),
]


class HTTPMetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware que cuenta errores HTTP 4xx/5xx.
    
    Args:
        app: ASGI app
        scope: Scope identifier for metrics (default: "auth")
        route_patterns: List of regex patterns to match (default: Auth routes)
        enabled: Whether the middleware is active (default: True)
    """
    
    def __init__(
        self,
        app,
        scope: str = "auth",
        route_patterns: Optional[List[Pattern]] = None,
        enabled: bool = True,
    ):
        super().__init__(app)
        self.scope = scope
        self.route_patterns = route_patterns or AUTH_ROUTE_PATTERNS
        self.enabled = enabled
        self._store = get_http_metrics_store()
    
    def _should_track(self, path: str) -> bool:
        """Check if the request path should be tracked."""
        for pattern in self.route_patterns:
            if pattern.match(path):
                return True
        return False
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and track error responses."""
        if not self.enabled:
            return await call_next(request)
        
        path = request.url.path
        
        # Only track matching routes
        if not self._should_track(path):
            return await call_next(request)
        
        response = await call_next(request)
        
        # Track 4xx and 5xx responses
        status_code = response.status_code
        if 400 <= status_code < 600:
            await self._store.increment(self.scope, status_code)
            logger.debug(
                "http_metrics_tracked path=%s status=%d scope=%s",
                path, status_code, self.scope
            )
        
        return response
