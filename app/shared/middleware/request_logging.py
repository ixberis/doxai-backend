# -*- coding: utf-8 -*-
"""
backend/app/shared/middleware/request_logging.py

Middleware para logging de requests HTTP con método, path, status y duración.

Garantiza visibilidad de requests en Railway logs.

Autor: DoxAI
Fecha: 2026-01-28
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Callable, List, Optional, Pattern
import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .exception_handler import get_request_id

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware que loguea inicio/fin de requests con métricas básicas.
    
    Loguea a stdout/stderr para visibilidad en Railway.
    
    Args:
        app: ASGI app
        include_patterns: Lista de regex patterns a incluir (default: todas)
        exclude_patterns: Lista de regex patterns a excluir (default: /metrics, /health)
    """
    
    DEFAULT_EXCLUDE = [
        re.compile(r"^/metrics"),
        re.compile(r"^/health"),
        re.compile(r"^/favicon\.ico"),
    ]
    
    def __init__(
        self,
        app,
        include_patterns: Optional[List[Pattern]] = None,
        exclude_patterns: Optional[List[Pattern]] = None,
    ):
        super().__init__(app)
        self.include_patterns = include_patterns
        self.exclude_patterns = exclude_patterns or self.DEFAULT_EXCLUDE
    
    def _should_log(self, path: str) -> bool:
        """Determina si el request debe loguearse."""
        # Primero verificar exclusiones
        for pattern in self.exclude_patterns:
            if pattern.match(path):
                return False
        
        # Si hay include_patterns, debe matchear al menos uno
        if self.include_patterns:
            for pattern in self.include_patterns:
                if pattern.match(path):
                    return True
            return False
        
        # Por defecto, loguear todo lo no excluido
        return True
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        
        if not self._should_log(path):
            return await call_next(request)
        
        method = request.method
        
        # Ensure request_id is set (use existing or generate via get_request_id)
        request_id = getattr(request.state, "request_id", None)
        if not request_id:
            request_id = get_request_id(request)
            request.state.request_id = request_id
        
        start = time.perf_counter()
        
        # Log inicio (stderr con flush para Railway)
        print(
            f"REQUEST_START request_id={request_id} method={method} path={path}",
            file=sys.stderr,
            flush=True,
        )
        
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception as e:
            status = 500
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            
            # Log fin (stderr con flush para Railway)
            log_line = (
                f"REQUEST_END request_id={request_id} method={method} path={path} "
                f"status={status} duration_ms={duration_ms:.2f}"
            )
            print(log_line, file=sys.stderr, flush=True)
            
            # También a logger estructurado
            logger.info(
                "request_completed request_id=%s method=%s path=%s status=%d duration_ms=%.2f",
                request_id,
                method,
                path,
                status,
                duration_ms,
            )
        
        return response


__all__ = ["RequestLoggingMiddleware"]
