# -*- coding: utf-8 -*-
"""
backend/app/shared/middleware/timing_middleware.py

Middleware para medir y logear tiempos de respuesta por ruta.

Updated: 2026-01-11 - Added gap_ms calculation for unaccounted latency diagnosis

Autor: DoxAI
Fecha: 2025-01-07
"""

import logging
import os
import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Threshold for logging gap warnings (ms)
GAP_WARNING_THRESHOLD_MS = float(os.environ.get("GAP_WARNING_THRESHOLD_MS", "500"))


def _format_timing(value) -> str:
    """
    Safely format a timing value for logging.
    Never breaks - returns str(v) on any error.
    """
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _safe_get_float(state, attr: str, default: float = 0.0) -> float:
    """Safely get a float from request.state."""
    try:
        val = getattr(state, attr, None)
        if val is None:
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


class TimingMiddleware(BaseHTTPMiddleware):
    """
    Middleware que registra tiempos de respuesta por endpoint.
    
    Logs estructurados:
    - route_completed: al finalizar, con duration_ms y gap_ms analysis
    
    Gap Analysis:
    - Reads auth_dep_total_ms (from auth dependencies)
    - Reads route_handler_ms (from RequestTelemetry.finalize)
    - Calculates gap_ms = duration_ms - (auth_dep_total_ms + route_handler_ms)
    - Logs warning if gap_ms > GAP_WARNING_THRESHOLD_MS
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
            
            # Calcular duración total del middleware
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            # Log fin con duración (solo para API routes)
            if path.startswith("/api"):
                # WARN for slow requests (>1s), INFO otherwise
                log_level = logging.WARNING if duration_ms > 1000 else logging.INFO
                
                # ═══════════════════════════════════════════════════════════════
                # Extract timing breakdown from request.state
                # ═══════════════════════════════════════════════════════════════
                extra_timings = ""
                
                # Primary breakdown timings
                db_exec_ms = _safe_get_float(request.state, "db_exec_ms")
                rate_limit_ms = _safe_get_float(request.state, "rate_limit_total_ms")
                
                if db_exec_ms > 0:
                    extra_timings += f" db_exec_ms={_format_timing(db_exec_ms)}"
                if rate_limit_ms > 0:
                    extra_timings += f" rate_limit_total_ms={_format_timing(rate_limit_ms)}"
                
                # ═══════════════════════════════════════════════════════════════
                # GAP ANALYSIS: Calculate unaccounted time
                # ═══════════════════════════════════════════════════════════════
                # auth_dep_total_ms: set by token_service (via auth_timings)
                auth_timings_raw = getattr(request.state, "auth_timings", None)
                # Validate auth_timings is dict before accessing
                auth_timings = auth_timings_raw if isinstance(auth_timings_raw, dict) else {}
                auth_dep_total_ms = float(auth_timings.get("auth_dep_total_ms", 0)) if auth_timings else 0
                
                # route_handler_ms: set by RequestTelemetry.finalize
                route_handler_ms = _safe_get_float(request.state, "route_handler_ms")
                
                # Calculate gap
                accounted_ms = auth_dep_total_ms + route_handler_ms
                gap_ms = max(0, duration_ms - accounted_ms)
                
                # Add gap analysis to log if significant
                if auth_dep_total_ms > 0 or route_handler_ms > 0:
                    extra_timings += f" auth_dep_ms={_format_timing(auth_dep_total_ms)}"
                    extra_timings += f" handler_ms={_format_timing(route_handler_ms)}"
                    extra_timings += f" gap_ms={_format_timing(gap_ms)}"
                    
                    # Log warning if gap is significant
                    if gap_ms > GAP_WARNING_THRESHOLD_MS:
                        logger.warning(
                            "timing_gap_detected path=%s gap_ms=%.2f duration_ms=%.2f auth_dep_ms=%.2f handler_ms=%.2f",
                            path, gap_ms, duration_ms, auth_dep_total_ms, route_handler_ms
                        )
                
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
