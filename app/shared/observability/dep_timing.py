# -*- coding: utf-8 -*-
"""
backend/app/shared/observability/dep_timing.py

Utility for recording dependency factory timing into request.state.

Used by FastAPI dependency factories to track resolution time,
enabling gap analysis in timing_middleware.

Autor: DoxAI
Fecha: 2026-01-11
"""

from __future__ import annotations

from fastapi import Request


def record_dep_timing(request: Request, name: str, elapsed_ms: float) -> None:
    """
    Record a dependency factory timing into request.state.dep_timings.
    
    Idempotent: creates dict if not exists, appends to existing.
    
    Args:
        request: FastAPI Request object
        name: Timing key (e.g., "dep_factory.projects_query_service_ms")
        elapsed_ms: Elapsed time in milliseconds
    
    Example:
        start = time.perf_counter()
        svc = MyService(db)
        elapsed_ms = (time.perf_counter() - start) * 1000
        record_dep_timing(request, "dep_factory.my_service_ms", elapsed_ms)
    """
    if not hasattr(request.state, "dep_timings"):
        request.state.dep_timings = {}
    request.state.dep_timings[name] = elapsed_ms


__all__ = ["record_dep_timing"]
