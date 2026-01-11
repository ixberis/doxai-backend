# -*- coding: utf-8 -*-
"""
backend/app/shared/observability/timed_route.py

TimedAPIRoute: Custom APIRoute that provides FALLBACK handler timing instrumentation.

PURPOSE:
    This class is a FALLBACK mechanism for routes that don't use manual telemetry
    (RequestTelemetry or LoginTelemetry). It ensures request.state.route_handler_ms
    is always populated for TimingMiddleware gap analysis.

BEHAVIOR:
    - Measures handler execution time (start to response)
    - Sets request.state.route_handler_ms ONLY if not already set by telemetry
    - Does NOT override values set by LoginTelemetry.finalize() or RequestTelemetry.finalize()

USAGE:
    Apply to routers where manual telemetry is not used, or as a safety net:
    
        router = APIRouter(
            prefix="/auth",
            tags=["auth"],
            route_class=TimedAPIRoute,
        )

SCOPE:
    Currently applied to auth routers (auth_tokens, auth_public, auth_admin).
    NOT applied globally to avoid interference with manually instrumented routes.

Autor: DoxAI
Fecha: 2026-01-11
"""

import time
from typing import Callable

from fastapi import Request
from fastapi.routing import APIRoute
from starlette.responses import Response


class TimedAPIRoute(APIRoute):
    """
    Fallback APIRoute that measures handler execution time.
    
    Sets request.state.route_handler_ms for TimingMiddleware gap analysis,
    but ONLY if not already set by RequestTelemetry or LoginTelemetry.
    
    This ensures no double measurement occurs when manual telemetry is used.
    """
    
    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()
        
        async def timed_route_handler(request: Request) -> Response:
            start = time.perf_counter()
            try:
                response = await original_route_handler(request)
                return response
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                # FALLBACK: Only set if not already populated by telemetry
                existing = getattr(request.state, "route_handler_ms", None)
                if existing is None or existing == 0:
                    request.state.route_handler_ms = elapsed_ms
        
        return timed_route_handler


__all__ = ["TimedAPIRoute"]
