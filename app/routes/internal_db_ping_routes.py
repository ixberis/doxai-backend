# -*- coding: utf-8 -*-
"""
backend/app/routes/internal_db_ping_routes.py

Endpoint de diagnóstico temporal para aislar latencia de conexión vs. query.

PATH: /api/_internal/db/ping  (y /_internal/db/ping en root)
Método: GET
Protegido: 
  - Authorization: Bearer <APP_SERVICE_TOKEN>
  - X-Service-Token: <APP_SERVICE_TOKEN>

Respuesta:
  - pool_checkout_ms: tiempo para obtener conexión lista del pool (checkout + readiness)
  - exec_ms: tiempo de SELECT 1
  - total_ms: tiempo total del handler
  - db_server_addr: inet_server_addr() (opcional)
  - db_client_addr: inet_client_addr() (opcional)

NOTA: Endpoint temporal/diagnóstico. Mantener limpio y seguro.

Autor: DoxAI
Fecha: 2026-01-11
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_async_session
from app.shared.internal_auth import InternalServiceAuth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/_internal/db", tags=["internal-db-diagnostics"])


class DbPingResponse(BaseModel):
    """Respuesta del endpoint de ping."""
    pool_checkout_ms: float  # Tiempo de checkout + connection ready
    exec_ms: float           # Tiempo de SELECT 1
    total_ms: float          # Tiempo total del handler
    db_server_addr: Optional[str] = None
    db_client_addr: Optional[str] = None


@router.get(
    "/ping",
    response_model=DbPingResponse,
    summary="DB ping diagnóstico",
    description=(
        "Mide latencia de pool checkout y ejecución SELECT 1. "
        "Requiere Authorization: Bearer <token> o X-Service-Token header."
    ),
)
async def db_ping(
    request: Request,
    _auth: InternalServiceAuth,
    session: AsyncSession = Depends(get_async_session),
) -> DbPingResponse:
    """
    Endpoint de diagnóstico para medir latencia de DB.
    
    Mide por separado:
    1. pool_checkout_ms: tiempo de await session.connection() 
       (incluye checkout del pool + connection readiness)
    2. exec_ms: tiempo de SELECT 1
    
    Setea request.state.db_exec_ms para que timing_middleware lo muestre.
    """
    total_start = time.perf_counter()
    
    try:
        # 1. Medir pool checkout (obtener conexión subyacente lista)
        checkout_start = time.perf_counter()
        conn = await session.connection()
        checkout_end = time.perf_counter()
        pool_checkout_ms = (checkout_end - checkout_start) * 1000
        
        # 2. Medir ejecución de SELECT 1
        exec_start = time.perf_counter()
        await session.execute(text("SELECT 1"))
        exec_end = time.perf_counter()
        exec_ms = (exec_end - exec_start) * 1000
        
        # 3. Obtener direcciones de servidor/cliente (best-effort)
        db_server_addr: Optional[str] = None
        db_client_addr: Optional[str] = None
        try:
            addr_result = await session.execute(
                text("SELECT inet_server_addr()::text AS srv, inet_client_addr()::text AS cli")
            )
            row = addr_result.mappings().fetchone()
            if row:
                db_server_addr = row.get("srv")
                db_client_addr = row.get("cli")
        except Exception:
            # No fallar si no se pueden obtener direcciones
            pass
        
        total_ms = (time.perf_counter() - total_start) * 1000
        
        # Setear en request.state para timing_middleware
        request.state.db_exec_ms = exec_ms
        
        return DbPingResponse(
            pool_checkout_ms=round(pool_checkout_ms, 2),
            exec_ms=round(exec_ms, 2),
            total_ms=round(total_ms, 2),
            db_server_addr=db_server_addr,
            db_client_addr=db_client_addr,
        )
        
    except Exception as e:
        total_ms = (time.perf_counter() - total_start) * 1000
        # Log seguro: solo tipo de excepción, sin mensaje (posibles secretos)
        logger.exception(
            "db_ping_failed: %s (elapsed=%.2fms)",
            type(e).__name__,
            total_ms,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"DB ping failed: {type(e).__name__}",
        )
