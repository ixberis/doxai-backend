# -*- coding: utf-8 -*-
"""
backend/app/shared/middleware/exception_handler.py

Middleware ASGI para capturar excepciones no manejadas y responder JSON.

Garantiza que cualquier error 500 devuelva JSON estructurado en lugar de text/plain,
incluyendo error_code y request_id para trazabilidad.

Autor: DoxAI
Fecha: 2026-01-28
"""

from __future__ import annotations

import logging
import sys
import traceback
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# Header para request ID (Railway, nginx, etc.)
REQUEST_ID_HEADERS = ["x-request-id", "x-railway-request-id", "x-correlation-id"]


def get_request_id(request: Request) -> str:
    """Extrae request_id de headers o genera uno nuevo."""
    for header in REQUEST_ID_HEADERS:
        value = request.headers.get(header)
        if value:
            return value
    return uuid.uuid4().hex[:16]  # 16-char hex fallback (lower collision)


class JSONExceptionMiddleware(BaseHTTPMiddleware):
    """
    Middleware que captura excepciones no manejadas y devuelve JSON.
    
    Garantiza:
    - Content-Type: application/json (nunca text/plain)
    - error_code estable para UI
    - request_id para correlación de logs
    - Stack trace en stderr para Railway
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = get_request_id(request)
        
        # Inyectar request_id en state para uso downstream
        request.state.request_id = request_id
        
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            # Capturar stack trace completo
            tb = traceback.format_exc()
            
            # Log a stderr con flush para Railway
            error_msg = (
                f"UNHANDLED_EXCEPTION request_id={request_id} "
                f"method={request.method} path={request.url.path} "
                f"error={repr(e)}"
            )
            print(error_msg, file=sys.stderr, flush=True)
            print(tb, file=sys.stderr, flush=True)
            
            # También a logger para consistencia
            logger.error(
                "unhandled_exception request_id=%s method=%s path=%s error=%s",
                request_id,
                request.method,
                request.url.path,
                repr(e),
            )
            
            # Response JSON estructurada
            detail = {
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "Internal server error",
                "request_id": request_id,
            }
            
            return JSONResponse(
                status_code=500,
                content={"detail": detail},
                headers={"X-Request-ID": request_id},
            )


__all__ = ["JSONExceptionMiddleware", "get_request_id"]
