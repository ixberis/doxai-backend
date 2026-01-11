# -*- coding: utf-8 -*-
"""
backend/app/routes/internal_db_user_query_routes.py

Endpoint interno de diagnóstico para medir la query de usuario por email.
Replica EXACTAMENTE la misma consulta que usa login (UserService.get_by_email),
sin password verify, sin sesión, sin audit.

Propósito:
- Aislar si la latencia (db_exec_ms ~2–3s en login) es por la query DB o por otro tramo.
- Comparar con /api/_internal/db/ping (~60ms) para determinar cuello de botella.

Autor: DoxAI
Fecha: 2026-01-11
"""

from __future__ import annotations

import logging
import time
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_async_session
from app.shared.internal_auth import InternalServiceAuth
from app.modules.auth.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/_internal/db", tags=["internal-diagnostics"])


@router.get(
    "/user-by-email",
    summary="Diagnóstico: query de usuario por email",
    description=(
        "Mide exactamente la misma consulta DB que usa login (get_by_email). "
        "NO genera sesión, NO emite JWT, NO registra audit. "
        "Solo para diagnóstico de latencia."
    ),
    response_model=None,
    dependencies=[Depends(InternalServiceAuth())],
)
async def db_user_by_email_ping(
    request: Request,
    email: Annotated[str, Query(description="Email a buscar (se normalizará: strip + lower)")],
    explain_analyze: Annotated[bool, Query(description="Si true, ejecuta EXPLAIN ANALYZE y devuelve el plan")] = False,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Ejecuta la query de usuario por email y mide tiempos detallados.
    
    Respuesta:
    - pool_checkout_ms: tiempo de obtener conexión del pool (await session.connection())
    - prep_ms: tiempo de preparación (session scope + pre_query_guards)
    - exec_ms: tiempo de ejecución de la query SQL
    - total_ms: tiempo total del handler
    - found: bool indicando si se encontró el usuario
    - user_id: ID del usuario (si encontrado, sin PII adicional)
    - auth_user_id: UUID del usuario (si encontrado)
    - borrowed_session: True si usó sesión prestada (como login)
    - explain_plan: plan de ejecución (si explain_analyze=true)
    """
    total_start = time.perf_counter()
    
    # Normalizar email igual que login
    norm_email = (email or "").strip().lower()
    
    if not norm_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email es requerido",
        )
    
    try:
        # ─── Crear UserService con la sesión del request (IGUAL que login) ───
        # LoginFlowService hace: self.user_service = UserService.with_session(db)
        user_service = UserService.with_session(db)
        
        # ─── Ejecutar get_by_email con return_timings=True (igual que login) ───
        result = await user_service.get_by_email(norm_email, return_timings=True)
        user, db_timings = result
        
        # Extraer tiempos del servicio
        pool_checkout_ms = db_timings.get("conn_checkout_ms", 0)
        prep_ms = db_timings.get("db_prep_ms", 0)
        exec_ms = db_timings.get("db_exec_ms", 0)
        borrowed_session = db_timings.get("borrowed_session", True)
        
        # Setear en request.state para timing_middleware
        request.state.db_exec_ms = exec_ms
        
        total_ms = (time.perf_counter() - total_start) * 1000
        
        response_data = {
            "pool_checkout_ms": round(pool_checkout_ms, 2),
            "prep_ms": round(prep_ms, 2),
            "exec_ms": round(exec_ms, 2),
            "total_ms": round(total_ms, 2),
            "found": user is not None,
            "user_id": getattr(user, "user_id", None) if user else None,
            "auth_user_id": str(getattr(user, "auth_user_id", None)) if user and getattr(user, "auth_user_id", None) else None,
            "borrowed_session": borrowed_session,
            "note": (
                "pool_checkout_ms=connection ready from pool (0 if borrowed), "
                "prep_ms=session setup, exec_ms=SQL execution time ONLY"
            ),
        }
        
        # ─── EXPLAIN ANALYZE opcional ───
        if explain_analyze:
            explain_data = await _run_explain_analyze(db, norm_email)
            response_data["explain_plan"] = explain_data
        
        return response_data
        
    except Exception as e:
        total_ms = (time.perf_counter() - total_start) * 1000
        logger.exception(
            "db_user_by_email_ping_failed: %s (elapsed=%.2fms)",
            type(e).__name__,
            total_ms,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"DB user query failed: {type(e).__name__}",
        )


@router.get(
    "/login-path-simulation",
    summary="Diagnóstico: simula el path exacto de login (sin password)",
    description=(
        "Replica EXACTAMENTE el path de login hasta después del user lookup. "
        "Incluye: rate limit checks (Redis) + DB query. "
        "NO hace password verify, NO emite JWT, NO registra sesión."
    ),
    response_model=None,
    dependencies=[Depends(InternalServiceAuth())],
)
async def login_path_simulation(
    request: Request,
    email: Annotated[str, Query(description="Email a buscar")],
    skip_rate_limit: Annotated[bool, Query(description="Si true, omite rate limit (solo mide DB)")] = False,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Simula el path de login completo para diagnóstico.
    
    Permite comparar:
    - Con skip_rate_limit=true: solo DB path
    - Con skip_rate_limit=false: rate limit + DB path (como login real)
    """
    from app.shared.security.rate_limit_service import get_rate_limiter
    
    total_start = time.perf_counter()
    timings = {}
    
    norm_email = (email or "").strip().lower()
    if not norm_email:
        raise HTTPException(status_code=400, detail="Email requerido")
    
    try:
        # ─── Fase 1: Rate Limit (opcional) ───
        if not skip_rate_limit:
            rate_limiter = get_rate_limiter()
            
            # Check email rate limit
            rl_email_start = time.perf_counter()
            email_result = await rate_limiter.check_and_consume_async(
                endpoint="auth:login",
                key_type="email",
                identifier=norm_email,
            )
            timings["rate_limit_email_ms"] = (time.perf_counter() - rl_email_start) * 1000
            
            # Check IP rate limit (simulated with fixed IP)
            rl_ip_start = time.perf_counter()
            ip_result = await rate_limiter.check_and_consume_async(
                endpoint="auth:login",
                key_type="ip",
                identifier="diagnostic-test",
            )
            timings["rate_limit_ip_ms"] = (time.perf_counter() - rl_ip_start) * 1000
            timings["rate_limit_total_ms"] = timings["rate_limit_email_ms"] + timings["rate_limit_ip_ms"]
        else:
            timings["rate_limit_email_ms"] = 0
            timings["rate_limit_ip_ms"] = 0
            timings["rate_limit_total_ms"] = 0
            timings["rate_limit_skipped"] = True
        
        # ─── Fase 2: DB Query (igual que login) ───
        user_service = UserService.with_session(db)
        result = await user_service.get_by_email(norm_email, return_timings=True)
        user, db_timings = result
        
        timings["conn_checkout_ms"] = db_timings.get("conn_checkout_ms", 0)
        timings["db_prep_ms"] = db_timings.get("db_prep_ms", 0)
        timings["db_exec_ms"] = db_timings.get("db_exec_ms", 0)
        timings["borrowed_session"] = db_timings.get("borrowed_session", True)
        
        timings["total_ms"] = (time.perf_counter() - total_start) * 1000
        
        # Setear en request.state
        request.state.db_exec_ms = timings["db_exec_ms"]
        request.state.rate_limit_total_ms = timings["rate_limit_total_ms"]
        
        return {
            **{k: round(v, 2) if isinstance(v, float) else v for k, v in timings.items()},
            "found": user is not None,
            "user_id": getattr(user, "user_id", None) if user else None,
            "analysis": _analyze_timings(timings),
        }
        
    except Exception as e:
        total_ms = (time.perf_counter() - total_start) * 1000
        logger.exception("login_path_simulation_failed: %s", type(e).__name__)
        raise HTTPException(status_code=503, detail=f"Simulation failed: {type(e).__name__}")


def _analyze_timings(timings: dict) -> dict:
    """Genera un análisis del breakdown de tiempos."""
    total = timings.get("total_ms", 1)
    
    rate_limit = timings.get("rate_limit_total_ms", 0)
    db_prep = timings.get("db_prep_ms", 0)
    db_exec = timings.get("db_exec_ms", 0)
    
    accounted = rate_limit + db_prep + db_exec
    unaccounted = total - accounted
    
    return {
        "rate_limit_pct": round(rate_limit / total * 100, 1) if total > 0 else 0,
        "db_prep_pct": round(db_prep / total * 100, 1) if total > 0 else 0,
        "db_exec_pct": round(db_exec / total * 100, 1) if total > 0 else 0,
        "unaccounted_ms": round(unaccounted, 2),
        "unaccounted_pct": round(unaccounted / total * 100, 1) if total > 0 else 0,
        "bottleneck": (
            "rate_limit" if rate_limit > db_prep and rate_limit > db_exec else
            "db_prep" if db_prep > db_exec else
            "db_exec"
        ),
    }


async def _run_explain_analyze(db: AsyncSession, email: str) -> dict:
    """
    Ejecuta EXPLAIN ANALYZE del SELECT de usuarios por email.
    Replica EXACTAMENTE la query real de login (columnas específicas + deleted_at IS NULL).
    Retorna el plan de ejecución limitado a 2000 caracteres.
    """
    try:
        explain_start = time.perf_counter()
        
        # Normalizar email igual que login: strip + lower
        norm_email = (email or "").strip().lower()
        
        # Query EXPLAIN con las mismas columnas que login realmente usa
        # Incluye deleted_at IS NULL para reflejar soft-delete real
        explain_sql = text("""
            EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT TEXT)
            SELECT 
                user_id, auth_user_id, user_email, user_password_hash, 
                user_is_activated, user_status, deleted_at
            FROM public.app_users 
            WHERE user_email = :email
              AND deleted_at IS NULL
            LIMIT 1
        """)
        
        result = await db.execute(explain_sql, {"email": norm_email})
        rows = result.fetchall()
        
        explain_ms = (time.perf_counter() - explain_start) * 1000
        
        # Convertir a lista de strings (cada fila del plan)
        plan_lines = [str(row[0]) for row in rows]
        plan_text = "\n".join(plan_lines)
        
        # Limitar a 2000 caracteres para evitar respuestas gigantes
        if len(plan_text) > 2000:
            plan_text = plan_text[:2000] + "\n... (truncated)"
        
        return {
            "explain_ms": round(explain_ms, 2),
            "plan": plan_text,
            "query_note": "Uses same columns as login: user_id, auth_user_id, user_email, user_password_hash, user_is_activated, user_status, deleted_at + WHERE deleted_at IS NULL",
        }
        
    except Exception as e:
        logger.warning("explain_analyze_failed: %s", type(e).__name__)
        return {
            "explain_ms": 0,
            "plan": f"EXPLAIN failed: {type(e).__name__}",
        }
