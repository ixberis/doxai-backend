# -*- coding: utf-8 -*-
"""
backend/app/shared/database/db_warmup.py

Warmup de base de datos para reducir latencia del primer request.

Este módulo ejecuta una query trivial (SELECT 1) al startup para:
- Forzar apertura de conexión física en el pool
- Completar handshake TLS con Postgres
- Precargar cualquier inicialización lazy del driver asyncpg

El warmup es best-effort: si falla, NO rompe el startup.

Autor: DoxAI
Fecha: 2026-01-12
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import text

logger = logging.getLogger("uvicorn.error")


@dataclass
class DbWarmupResult:
    """
    Resultado del warmup de base de datos.
    
    Attributes:
        success: True si el warmup completó correctamente
        duration_ms: Tiempo total del warmup en milisegundos
        error: Mensaje de error si success=False
        skipped: True si el warmup fue omitido (ej. SKIP_DB_INIT=1)
    """
    success: bool
    duration_ms: float
    error: Optional[str] = None
    skipped: bool = False


async def warmup_db_async() -> DbWarmupResult:
    """
    Ejecuta warmup de base de datos al startup.
    
    Abre una sesión real del pool y ejecuta SELECT 1 para:
    - Forzar creación de conexión física
    - Completar handshake TLS
    - Ejecutar inicialización de conexión (statement_timeout, etc.)
    
    Returns:
        DbWarmupResult con métricas de éxito/fallo y duración.
    
    Note:
        Este método es best-effort y NUNCA levanta excepciones.
        Si falla, retorna success=False con el error en el campo error.
    """
    start_time = time.perf_counter()
    
    logger.info("db_warmup_started")
    
    try:
        # Import tardío para evitar ciclos y respetar SKIP_DB_INIT
        from app.shared.database.database import SessionLocal, SKIP_DB_INIT
        
        if SKIP_DB_INIT:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "db_warmup_skipped reason=SKIP_DB_INIT duration_ms=%.2f",
                duration_ms
            )
            return DbWarmupResult(
                success=True,
                duration_ms=duration_ms,
                skipped=True
            )
        
        if SessionLocal is None:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.warning(
                "db_warmup_skipped reason=SessionLocal_not_initialized duration_ms=%.2f",
                duration_ms
            )
            return DbWarmupResult(
                success=False,
                duration_ms=duration_ms,
                error="SessionLocal not initialized"
            )
        
        # Crear sesión real y ejecutar query trivial
        async with SessionLocal() as session:
            # SELECT 1 es la query más simple posible
            # Fuerza: checkout de conexión, handshake TLS, init de conexión
            await session.execute(text("SELECT 1"))
            # No necesitamos commit para SELECT, pero cerramos limpiamente
        
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "db_warmup_success duration_ms=%.2f",
            duration_ms
        )
        
        return DbWarmupResult(
            success=True,
            duration_ms=duration_ms
        )
        
    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        error_msg = str(e)
        
        logger.warning(
            "db_warmup_failed error=%s duration_ms=%.2f",
            error_msg,
            duration_ms
        )
        
        return DbWarmupResult(
            success=False,
            duration_ms=duration_ms,
            error=error_msg
        )


__all__ = [
    "DbWarmupResult",
    "warmup_db_async",
]
