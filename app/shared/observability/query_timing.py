# -*- coding: utf-8 -*-
"""
backend/app/shared/observability/query_timing.py

Context manager and utilities for measuring query execution time.

Autor: DoxAI
Fecha: 2025-01-07
"""

import logging
import time

logger = logging.getLogger(__name__)

__all__ = ["QueryTimingContext", "timed_execute"]


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
