# -*- coding: utf-8 -*-
"""
backend/app/shared/observability/request_telemetry.py

RequestTelemetry: Generic timing and diagnostics for route handlers.

Reusable pattern similar to LoginTelemetry but for any route.

Features:
- Single structured log event (route_timing_breakdown)
- Threshold-based INFO/DEBUG gating
- Consistent request.state population for middleware
- Calculates unaccounted_ms to identify gaps

Autor: DoxAI
Fecha: 2026-01-11
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional

logger = logging.getLogger(__name__)

# Configurable via env: default 1200ms
SLOW_ROUTE_THRESHOLD_MS = float(os.environ.get("SLOW_ROUTE_THRESHOLD_MS", "1200"))

# Debug flag to force INFO logging for all routes
ROUTE_TELEMETRY_DEBUG = os.environ.get("ROUTE_TELEMETRY_DEBUG", "0").lower() in ("1", "true", "yes")

# Result types for structured logging
RouteResult = Literal["success", "error", "validation_error", "not_found", "unauthorized", "http_error"]


@dataclass
class RequestTelemetry:
    """
    Generic telemetry collector for route handlers.
    
    Usage:
        telemetry = RequestTelemetry.create("projects.active-projects")
        
        with telemetry.measure("auth_ms"):
            auth_user_id = get_auth_user_id(user)
        
        with telemetry.measure("db_ms"):
            items = await query_service.list_items(...)
        
        with telemetry.measure("ser_ms"):
            response = serialize(items)
        
        telemetry.finalize(request, status_code=200, result="success")
    """
    
    route_name: str = ""
    start_time: float = field(default_factory=time.perf_counter)
    timings: Dict[str, float] = field(default_factory=dict)
    flags: Dict[str, Any] = field(default_factory=dict)
    _finalized: bool = field(default=False, repr=False)
    
    @classmethod
    def create(cls, route_name: str) -> "RequestTelemetry":
        """Factory method with route name."""
        return cls(route_name=route_name)
    
    def mark_timing(self, name: str, value_ms: float) -> None:
        """Record a timing value in milliseconds."""
        self.timings[name] = value_ms
    
    def set_flag(self, name: str, value: Any) -> None:
        """Set a diagnostic flag."""
        self.flags[name] = value
    
    class TimingContext:
        """Context manager for measuring a timing."""
        
        def __init__(self, telemetry: "RequestTelemetry", name: str):
            self.telemetry = telemetry
            self.name = name
            self.start: float = 0
        
        def __enter__(self) -> "RequestTelemetry.TimingContext":
            self.start = time.perf_counter()
            return self
        
        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            elapsed_ms = (time.perf_counter() - self.start) * 1000
            self.telemetry.mark_timing(self.name, elapsed_ms)
            return None  # Don't suppress exceptions
    
    def measure(self, name: str) -> TimingContext:
        """Create a context manager for timing a block."""
        return self.TimingContext(self, name)
    
    def finalize(
        self,
        request: Optional[Any],
        status_code: int = 200,
        result: RouteResult = "success",
    ) -> Dict[str, Any]:
        """
        Finalize telemetry: calculate total, set request.state, emit log.
        
        MUST be called in all exit paths (success, error, exception).
        
        Incorporates auth_timings from request.state.auth_timings if present.
        
        Args:
            request: FastAPI Request object (can be None)
            status_code: HTTP status code
            result: Route result for logging
            
        Returns:
            Dict with all timings and flags for optional diagnostics
        """
        if self._finalized:
            logger.warning("RequestTelemetry.finalize() called multiple times for route=%s", self.route_name)
            return self._build_summary()
        
        self._finalized = True
        
        # Calculate total
        self.timings["total_ms"] = (time.perf_counter() - self.start_time) * 1000
        
        # ═══════════════════════════════════════════════════════════════════════
        # Incorporate auth_timings from dependency (if present)
        # ═══════════════════════════════════════════════════════════════════════
        if request is not None:
            try:
                auth_timings = getattr(request.state, "auth_timings", None)
                if auth_timings and isinstance(auth_timings, dict):
                    # Copy auth timing fields as flags (not _ms to avoid skewing accounted)
                    self.flags["auth_dep_total_ms"] = auth_timings.get("auth_dep_total_ms", 0)
                    self.flags["auth_jwt_decode_ms"] = auth_timings.get("jwt_decode_ms", 0)
                    self.flags["auth_user_lookup_ms"] = auth_timings.get("user_lookup_ms", 0)
                    self.flags["auth_db_ms"] = auth_timings.get("auth_db_ms", 0)
                    self.flags["auth_mode"] = auth_timings.get("auth_mode", "unknown")
                    self.flags["auth_path"] = auth_timings.get("auth_path", "unknown")
            except Exception as e:
                logger.debug("Failed to read auth_timings: %s", str(e))
        
        # ═══════════════════════════════════════════════════════════════════════
        # Incorporate dep_timings from factories (pre-handler dependencies)
        # ═══════════════════════════════════════════════════════════════════════
        if request is not None:
            try:
                dep_timings = getattr(request.state, "dep_timings", None)
                if dep_timings and isinstance(dep_timings, dict):
                    # Calculate total deps_ms
                    deps_ms = sum(
                        v for v in dep_timings.values()
                        if isinstance(v, (int, float))
                    )
                    self.flags["deps_ms"] = deps_ms
                    # Include individual dep timings as flags for detailed breakdown
                    for k, v in dep_timings.items():
                        self.flags[k] = v
            except Exception as e:
                logger.debug("Failed to read dep_timings: %s", str(e))
        
        # Calculate accounted dynamically: sum all keys ending with _ms except meta keys
        meta_keys = {"total_ms", "accounted_ms", "overhead_ms"}
        accounted_ms = sum(
            v for k, v in self.timings.items() 
            if k.endswith("_ms") and k not in meta_keys and isinstance(v, (int, float))
        )
        overhead_ms = max(0, self.timings["total_ms"] - accounted_ms)
        
        self.timings["accounted_ms"] = accounted_ms
        self.timings["overhead_ms"] = overhead_ms
        
        # Set request.state for timing_middleware
        if request is not None:
            try:
                # Primary DB timing for middleware
                request.state.db_exec_ms = self.timings.get("db_ms", 0)
                # Redis timing if any
                request.state.redis_ms = self.timings.get("redis_ms", 0)
                # Full timings for observability (NOT serialized to response)
                request.state.request_timings = self.timings.copy()
                
                # ═══════════════════════════════════════════════════════════════
                # NEW: Set route_handler_ms for gap analysis in timing_middleware
                # This is the total time spent in the route handler (measured by telemetry)
                # ═══════════════════════════════════════════════════════════════
                request.state.route_handler_ms = self.timings.get("total_ms", 0)
                
            except Exception as e:
                logger.debug("Failed to set request.state: %s", str(e))
        
        # Emit structured log
        self._emit_log(status_code, result)
        
        return self._build_summary()
    
    def _build_summary(self) -> Dict[str, Any]:
        """Build summary dict with all timings and flags."""
        return {
            "timings": self.timings.copy(),
            "flags": self.flags.copy(),
        }
    
    def _emit_log(self, status_code: int, result: RouteResult) -> None:
        """
        Emit single structured log event.
        
        Rules:
        - INFO if: slow (>= threshold) OR error (status >= 400)
        - DEBUG for fast successful routes
        - Force INFO if ROUTE_TELEMETRY_DEBUG is enabled
        """
        total_ms = self.timings.get("total_ms", 0)
        is_error = status_code >= 400
        is_slow = total_ms >= SLOW_ROUTE_THRESHOLD_MS
        
        # Build timing string dynamically based on what was measured
        timing_parts = []
        for key in ["auth_ms", "user_ctx_ms", "db_ms", "redis_ms", "ser_ms", "policy_ms", "pre_ms"]:
            if key in self.timings and self.timings[key] > 0:
                timing_parts.append(f"{key}={self.timings[key]:.2f}")
        
        # Add calculated fields
        timing_str = " ".join(timing_parts)
        
        log_msg = (
            "route_timing_breakdown route=%s result=%s status=%d "
            "total_ms=%.2f accounted_ms=%.2f overhead_ms=%.2f %s"
        )
        log_args = (
            self.route_name,
            result,
            status_code,
            total_ms,
            self.timings.get("accounted_ms", 0),
            self.timings.get("overhead_ms", 0),
            timing_str,
        )
        
        # Build flags string (includes auth timings)
        flag_parts = []
        
        # Auth timings first (these explain the gap)
        auth_dep_ms = self.flags.get("auth_dep_total_ms", 0)
        if auth_dep_ms and auth_dep_ms > 0:
            flag_parts.append(f"auth_dep_total_ms={auth_dep_ms:.1f}")
            flag_parts.append(f"auth_lookup_ms={self.flags.get('auth_user_lookup_ms', 0):.1f}")
            flag_parts.append(f"auth_mode={self.flags.get('auth_mode', 'unknown')}")
        
        # Other flags
        for k, v in self.flags.items():
            if k.startswith("auth_"):
                continue  # Already handled above
            flag_parts.append(f"{k}={v}")
        
        if flag_parts:
            flags_str = " ".join(flag_parts)
            log_msg += " %s"
            log_args = (*log_args, flags_str)
        
        # Determine log level
        use_info = ROUTE_TELEMETRY_DEBUG or is_slow or is_error
        
        if use_info:
            logger.info(log_msg, *log_args)
        else:
            logger.debug(log_msg, *log_args)


__all__ = ["RequestTelemetry", "RouteResult", "SLOW_ROUTE_THRESHOLD_MS"]
