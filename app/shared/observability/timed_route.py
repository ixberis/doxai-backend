# -*- coding: utf-8 -*-
"""
backend/app/shared/observability/timed_route.py

TimedAPIRoute: Custom APIRoute that automatically instruments handler timing.

Sets request.state.route_handler_ms for TimingMiddleware gap analysis.

This is the structural solution for routes that don't use RequestTelemetry manually.

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
    Custom APIRoute that wraps the endpoint to measure handler execution time.
    
    Sets request.state.route_handler_ms which is read by TimingMiddleware
    for accurate gap analysis.
    
    Usage:
        router = APIRouter(
            prefix="/auth",
            tags=["auth"],
            route_class=TimedAPIRoute,
        )
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
                # Set handler timing for TimingMiddleware
                # Only set if not already set by RequestTelemetry/LoginTelemetry
                if not hasattr(request.state, "route_handler_ms") or request.state.route_handler_ms == 0:
                    request.state.route_handler_ms = elapsed_ms
        
        return timed_route_handler


__all__ = ["TimedAPIRoute"]
