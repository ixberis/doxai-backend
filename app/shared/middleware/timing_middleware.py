# -*- coding: utf-8 -*-
"""
backend/app/shared/middleware/timing_middleware.py

Middleware para medir y logear tiempos de respuesta por ruta.

Updated: 2026-01-11 - Mediciones contiguas sin micro-gaps

Pipeline para /api/* routes:
1. mw_pre_call_next_ms
2. call_next_ms
3. AFTER (post-processing) - mediciones contiguas desde after_start:
   3.1 BUILD → mw_after_build_ms (from after_start to build_end)
   3.2 WARN (solo si warning real) → mw_after_warn_ms (0 si no hay warning)
   3.3 HEADERS → mw_after_headers_ms (incluye medición de actual_final_duration_ms)
   === MEASUREMENT POINT: actual_final_duration_ms (= duration_ms = X-Response-Time-Ms) ===
   3.4 LOG route_completed → mw_after_log_ms
   3.5 AFTER totals

mw_after_total_to_duration_ms = build + warn + headers (suma de componentes)
mw_after_total_to_duration_ms_measured = (final_end_for_duration - after_start) * 1000 (medición real)
gap_total_ms usa mw_after_total_to_duration_ms para consistencia con duration_ms

Autor: DoxAI
Fecha: 2025-01-07
"""

import logging
import os
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing import Callable

logger = logging.getLogger(__name__)

GAP_WARNING_THRESHOLD_MS = float(os.environ.get("GAP_WARNING_THRESHOLD_MS", "500"))


def _format_timing(value) -> str:
    """Safely format a timing value for logging."""
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
    
    Objetivo: aislar el gap de latencia 200-300ms separando:
    - Lo que ocurre DENTRO de call_next (auth, deps, handler)
    - Lo que ocurre DESPUÉS (post-processing del middleware)
    
    Métricas clave:
    - gap_call_next_ms: tiempo no explicado dentro de call_next
    - gap_total_ms: tiempo no explicado en el total (excluyendo el log)
    - mw_after_log_ms: overhead del logging (puede ser 50-150ms en Railway)
    """
    
    EXCLUDE_PATHS = {"/health", "/healthz", "/ready", "/metrics", "/favicon.ico"}
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        
        if path in self.EXCLUDE_PATHS or path.startswith("/static"):
            return await call_next(request)
        
        method = request.method
        start_time = time.perf_counter()
        
        # ═══════════════════════════════════════════════════════════════
        # SEGMENT 1: mw_pre_call_next_ms
        # ═══════════════════════════════════════════════════════════════
        pre_call_next_end = time.perf_counter()
        mw_pre_call_next_ms = (pre_call_next_end - start_time) * 1000
        
        try:
            # ═══════════════════════════════════════════════════════════════
            # SEGMENT 2: call_next_ms
            # ═══════════════════════════════════════════════════════════════
            call_next_start = time.perf_counter()
            response = await call_next(request)
            call_next_end = time.perf_counter()
            call_next_ms = (call_next_end - call_next_start) * 1000
            
            # ═══════════════════════════════════════════════════════════════
            # SEGMENT 3: mw_after - post-processing (mediciones contiguas)
            # after_start = call_next_end (NOT a new perf_counter)
            # ═══════════════════════════════════════════════════════════════
            after_start = call_next_end
            
            if path.startswith("/api"):
                # ═══════════════════════════════════════════════════════════
                # PHASE 3.1: BUILD - extract timings, calculate gaps
                # Medición contigua desde after_start
                # ═══════════════════════════════════════════════════════════
                db_exec_ms = _safe_get_float(request.state, "db_exec_ms")
                rate_limit_ms = _safe_get_float(request.state, "rate_limit_total_ms")
                
                dep_timings_raw = getattr(request.state, "dep_timings", None)
                dep_timings = dep_timings_raw if isinstance(dep_timings_raw, dict) else {}
                deps_ms = sum(v for v in dep_timings.values() if isinstance(v, (int, float)))
                
                auth_timings_raw = getattr(request.state, "auth_timings", None)
                auth_timings = auth_timings_raw if isinstance(auth_timings_raw, dict) else {}
                auth_dep_ms = float(auth_timings.get("auth_dep_total_ms", 0)) if auth_timings else 0
                
                # db_dep_total_ms: atributo separado de get_db_timed (NO suma a deps_ms)
                db_dep_total_ms = _safe_get_float(request.state, "db_dep_total_ms")
                
                handler_ms = _safe_get_float(request.state, "route_handler_ms")
                call_next_minus_handler_ms = max(0, call_next_ms - handler_ms) if handler_ms > 0 else 0
                
                # gap_call_next_ms: unaccounted within call_next
                accounted_in_call_next = auth_dep_ms + deps_ms + handler_ms
                gap_call_next_ms = max(0, call_next_ms - accounted_in_call_next)
                
                has_gap_analysis = auth_dep_ms > 0 or handler_ms > 0 or deps_ms > 0
                log_level = logging.WARNING if (time.perf_counter() - start_time) * 1000 > 1000 else logging.INFO
                
                build_end = time.perf_counter()
                # Medición contigua desde after_start (no desde build_start)
                mw_after_build_ms = (build_end - after_start) * 1000
                
                # ═══════════════════════════════════════════════════════════
                # PHASE 3.2: WARN - timing_gap_detected if significant
                # mw_after_warn_ms = 0 if NO warning is emitted
                # ═══════════════════════════════════════════════════════════
                mw_after_warn_ms = 0.0
                warn_end = build_end  # Si no hay warning, warn_end = build_end
                
                if gap_call_next_ms > GAP_WARNING_THRESHOLD_MS:
                    dep_detail = " ".join(f"{k}={v:.2f}" for k, v in dep_timings.items()) if dep_timings else "none"
                    logger.warning(
                        "timing_gap_detected path=%s gap_call_next_ms=%.2f call_next_ms=%.2f "
                        "auth_dep_ms=%.2f deps_ms=%.2f handler_ms=%.2f "
                        "call_next_minus_handler_ms=%.2f mw_pre_call_next_ms=%.2f "
                        "dep_breakdown=%s",
                        path, gap_call_next_ms, call_next_ms, auth_dep_ms, deps_ms, handler_ms,
                        call_next_minus_handler_ms, mw_pre_call_next_ms, dep_detail
                    )
                    warn_end = time.perf_counter()
                    mw_after_warn_ms = (warn_end - build_end) * 1000
                
                # ═══════════════════════════════════════════════════════════
                # PHASE 3.3: HEADERS - set X-Response-Time-Ms (final, una sola vez)
                # Punto de medición de actual_final_duration_ms
                # ═══════════════════════════════════════════════════════════
                # Medir duration AHORA (después de build y warn, antes de set header)
                final_end_for_duration = time.perf_counter()
                actual_final_duration_ms = (final_end_for_duration - start_time) * 1000
                
                # Medición real del tiempo desde after_start hasta este punto
                mw_after_total_to_duration_ms_measured = (final_end_for_duration - after_start) * 1000
                
                # Setear header con el valor final real - medir SOLO el set
                headers_start = time.perf_counter()
                response.headers["X-Response-Time-Ms"] = f"{actual_final_duration_ms:.2f}"
                headers_end = time.perf_counter()
                mw_after_headers_ms = (headers_end - headers_start) * 1000
                
                # ═══════════════════════════════════════════════════════════
                # === MEASUREMENT POINT: mw_after_total_to_duration_ms ===
                # Suma de componentes hasta el punto de duration
                # ═══════════════════════════════════════════════════════════
                mw_after_total_to_duration_ms = mw_after_build_ms + mw_after_warn_ms + mw_after_headers_ms
                mw_after_total_to_duration_drift_ms = max(0, mw_after_total_to_duration_ms_measured - mw_after_total_to_duration_ms)
                
                # gap_total_ms: usa scope consistente con duration_ms
                gap_total_ms = max(0, actual_final_duration_ms - (auth_dep_ms + deps_ms + handler_ms + mw_after_total_to_duration_ms))
                
                # ═══════════════════════════════════════════════════════════
                # PHASE 3.4: LOG - route_completed (UN SOLO LOG)
                # Este log usa actual_final_duration_ms (mismo valor que el header)
                # ═══════════════════════════════════════════════════════════
                log_start = time.perf_counter()
                
                # Build extra_timings string for logging
                extra_timings = ""
                if db_exec_ms > 0:
                    extra_timings += f" db_exec_ms={_format_timing(db_exec_ms)}"
                if rate_limit_ms > 0:
                    extra_timings += f" rate_limit_total_ms={_format_timing(rate_limit_ms)}"
                # Solo loggear db_dep_total_ms si > 1ms (evita ruido de 0.00 en canonical mode)
                if db_dep_total_ms > 1.0:
                    extra_timings += f" db_dep_total_ms={_format_timing(db_dep_total_ms)}"
                
                extra_timings += f" mw_pre_call_next_ms={_format_timing(mw_pre_call_next_ms)}"
                extra_timings += f" call_next_ms={_format_timing(call_next_ms)}"
                extra_timings += f" auth_dep_ms={_format_timing(auth_dep_ms)}"
                extra_timings += f" deps_ms={_format_timing(deps_ms)}"
                extra_timings += f" handler_ms={_format_timing(handler_ms)}"
                extra_timings += f" gap_call_next_ms={_format_timing(gap_call_next_ms)}"
                extra_timings += f" mw_after_build_ms={_format_timing(mw_after_build_ms)}"
                extra_timings += f" mw_after_warn_ms={_format_timing(mw_after_warn_ms)}"
                extra_timings += f" mw_after_headers_ms={_format_timing(mw_after_headers_ms)}"
                extra_timings += f" mw_after_total_to_duration_ms={_format_timing(mw_after_total_to_duration_ms)}"
                extra_timings += f" gap_total_ms={_format_timing(gap_total_ms)}"
                
                logger.log(
                    log_level,
                    "route_completed method=%s path=%s status=%d duration_ms=%.2f%s",
                    method,
                    path,
                    response.status_code,
                    actual_final_duration_ms,
                    extra_timings,
                )
                
                log_end = time.perf_counter()
                mw_after_log_ms = (log_end - log_start) * 1000
                
                # ═══════════════════════════════════════════════════════════
                # PHASE 3.5: AFTER totals (para DEBUG)
                # ═══════════════════════════════════════════════════════════
                after_end = time.perf_counter()
                mw_after_total_ms = (after_end - after_start) * 1000
                mw_after_sum_ms = mw_after_build_ms + mw_after_warn_ms + mw_after_headers_ms + mw_after_log_ms
                mw_after_drift_ms = max(0, mw_after_total_ms - mw_after_sum_ms)
                
                # Cuánto tiempo agrega el log después del punto de medición de duration
                after_end_to_duration_gap_ms = max(0, mw_after_total_ms - mw_after_total_to_duration_ms)
                
                # ═══════════════════════════════════════════════════════════
                # DEBUG: timing_summary con breakdown completo
                # ═══════════════════════════════════════════════════════════
                if has_gap_analysis:
                    logger.debug(
                        "timing_summary path=%s duration_ms=%.2f "
                        "mw_pre_call_next_ms=%.2f call_next_ms=%.2f "
                        "auth_dep_ms=%.2f deps_ms=%.2f handler_ms=%.2f "
                        "gap_call_next_ms=%.2f "
                        "mw_after_build_ms=%.2f mw_after_warn_ms=%.2f mw_after_headers_ms=%.2f "
                        "mw_after_log_ms=%.2f "
                        "mw_after_total_to_duration_ms=%.2f mw_after_total_to_duration_ms_measured=%.2f "
                        "mw_after_total_to_duration_drift_ms=%.2f "
                        "mw_after_total_ms=%.2f mw_after_sum_ms=%.2f mw_after_drift_ms=%.2f "
                        "gap_total_ms=%.2f after_end_to_duration_gap_ms=%.2f",
                        path, actual_final_duration_ms,
                        mw_pre_call_next_ms, call_next_ms,
                        auth_dep_ms, deps_ms, handler_ms,
                        gap_call_next_ms,
                        mw_after_build_ms, mw_after_warn_ms, mw_after_headers_ms,
                        mw_after_log_ms,
                        mw_after_total_to_duration_ms, mw_after_total_to_duration_ms_measured,
                        mw_after_total_to_duration_drift_ms,
                        mw_after_total_ms, mw_after_sum_ms, mw_after_drift_ms,
                        gap_total_ms, after_end_to_duration_gap_ms
                    )
            else:
                # Non-API routes: just set header
                final_duration_ms = (time.perf_counter() - start_time) * 1000
                response.headers["X-Response-Time-Ms"] = f"{final_duration_ms:.2f}"
            
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


# Re-exports for backward compatibility
from app.shared.observability.query_timing import QueryTimingContext, timed_execute

__all__ = [
    "TimingMiddleware",
    "QueryTimingContext",
    "timed_execute",
    "GAP_WARNING_THRESHOLD_MS",
]
