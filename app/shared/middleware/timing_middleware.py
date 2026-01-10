# -*- coding: utf-8 -*-
"""
backend/app/shared/middleware/timing_middleware.py

Middleware para medir y logear tiempos de respuesta por ruta.

Autor: DoxAI
Fecha: 2025-01-07
"""

import logging
import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


def _format_timing(value) -> str:
    """
    Safely format a timing value for logging.
    Never breaks - returns str(v) on any error.
    """
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


class TimingMiddleware(BaseHTTPMiddleware):
    """
    Middleware que registra tiempos de respuesta por endpoint.
    
    Logs estructurados:
    - route_started: al inicio del request
    - route_completed: al finalizar, con duration_ms
    """
    
    # Rutas a excluir del logging (health checks, static, etc.)
    EXCLUDE_PATHS = {"/health", "/healthz", "/ready", "/metrics", "/favicon.ico"}
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        
        # Excluir rutas de health/static
        if path in self.EXCLUDE_PATHS or path.startswith("/static"):
            return await call_next(request)
        
        method = request.method
        start_time = time.perf_counter()
        
        # Note: route_started logs removed to reduce volume (Railway rate limits)
        # Only route_completed is logged now
        
        try:
            response = await call_next(request)
            
            # Calcular duración
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            # Log fin con duración (solo para API routes)
            if path.startswith("/api"):
                # WARN for slow requests (>1s), INFO otherwise
                log_level = logging.WARNING if duration_ms > 1000 else logging.INFO
                
                # Extract breakdown timings from request.state (primary source)
                # Robust formatting: never break logging due to unexpected types
                extra_timings = ""
                
                db_exec = getattr(request.state, "db_exec_ms", None)
                rate_limit = getattr(request.state, "rate_limit_total_ms", None)
                
                if db_exec is not None:
                    extra_timings += f" db_exec_ms={_format_timing(db_exec)}"
                if rate_limit is not None:
                    extra_timings += f" rate_limit_total_ms={_format_timing(rate_limit)}"
                
                logger.log(
                    log_level,
                    "route_completed method=%s path=%s status=%d duration_ms=%.2f%s",
                    method,
                    path,
                    response.status_code,
                    duration_ms,
                    extra_timings,
                )
            
            # Agregar header para debugging
            response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"
            
            return response
            
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "route_error method=%s path=%s error=%s duration_ms=%.2f",
                method,
                path,
                str(e),
                duration_ms,
            )
            raise


class QueryTimingContext:
    """
    Context manager para medir tiempo de queries individuales.
    
    Uso:
        with QueryTimingContext("get_profile") as ctx:
            result = await db.execute(stmt)
        # ctx.duration_ms disponible después
    """
    
    def __init__(self, operation_name: str, log: bool = True):
        self.operation_name = operation_name
        self.log = log
        self.start_time: float = 0
        self.duration_ms: float = 0
    
    def __enter__(self) -> "QueryTimingContext":
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.duration_ms = (time.perf_counter() - self.start_time) * 1000
        
        if self.log:
            if exc_type is not None:
                logger.error(
                    "query_error operation=%s error=%s duration_ms=%.2f",
                    self.operation_name,
                    str(exc_val),
                    self.duration_ms,
                )
            elif self.duration_ms > 500:
                logger.warning(
                    "query_slow operation=%s duration_ms=%.2f",
                    self.operation_name,
                    self.duration_ms,
                )
            else:
                logger.debug(
                    "query_completed operation=%s duration_ms=%.2f",
                    self.operation_name,
                    self.duration_ms,
                )


async def timed_execute(db, stmt, operation_name: str = "query"):
    """
    Wrapper para ejecutar queries con timing.
    
    Uso:
        result = await timed_execute(db, stmt, "get_user_profile")
    """
    with QueryTimingContext(operation_name):
        return await db.execute(stmt)
