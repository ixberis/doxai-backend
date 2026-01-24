# -*- coding: utf-8 -*-
"""
backend/app/modules/files/metrics/collectors/delete_collectors.py

Prometheus collectors para operaciones de eliminación de archivos.

Métricas expuestas:
- files_delete_total{file_type, op, result} - Contador de operaciones delete
- files_delete_batch_size - Histogram de tamaño de batch
- files_delete_latency_seconds{file_type, op} - Histogram de latencia
- files_delete_partial_failures_total{file_type, op} - Counter de failures parciales
- files_delete_errors_total{file_type, status_code} - Counter de errores por status

Labels:
- file_type: "input" | "product"
- op: "single_delete" | "bulk_delete" | "cleanup_ghosts"
- result: "success" | "partial" | "failure"
- status_code: "404" | "409" | "500" | "503"

Autor: DoxAI
Fecha: 2026-01-23
"""
from __future__ import annotations

import logging
from typing import Optional

from app.shared.core.metrics_helpers import (
    get_or_create_counter,
    get_or_create_histogram,
)

_logger = logging.getLogger("files.delete.metrics")

# ---------------------------------------------------------------------------
# Metric names (Prometheus naming convention)
# ---------------------------------------------------------------------------
DELETE_TOTAL_NAME = "files_delete_total"
DELETE_BATCH_SIZE_NAME = "files_delete_batch_size"
DELETE_LATENCY_NAME = "files_delete_latency_seconds"
DELETE_PARTIAL_FAILURES_NAME = "files_delete_partial_failures_total"
DELETE_ERRORS_NAME = "files_delete_errors_total"

# ---------------------------------------------------------------------------
# Label names
# ---------------------------------------------------------------------------
LABELS_DELETE_TOTAL = ("file_type", "op", "result")
LABELS_LATENCY = ("file_type", "op")
LABELS_PARTIAL = ("file_type", "op")
LABELS_ERRORS = ("file_type", "status_code")

# ---------------------------------------------------------------------------
# Default histogram buckets
# ---------------------------------------------------------------------------
# Batch size buckets: 1, 2, 5, 10, 20, 50, 100, 200, 500
BATCH_SIZE_BUCKETS = (1, 2, 5, 10, 20, 50, 100, 200, 500, float("inf"))

# Latency buckets in seconds: 10ms to 30s
LATENCY_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, float("inf"))

# ---------------------------------------------------------------------------
# Lazy initialization
# ---------------------------------------------------------------------------
_collectors_initialized = False
_delete_total: Optional[object] = None
_delete_batch_size: Optional[object] = None
_delete_latency: Optional[object] = None
_delete_partial_failures: Optional[object] = None
_delete_errors: Optional[object] = None


def _ensure_collectors() -> bool:
    """
    Inicializa los collectors de Prometheus de forma lazy.
    
    Los counters/histograms aparecerán en /metrics con TYPE/HELP al registrarse.
    Los valores con labels aparecen cuando hay actividad real (no se pre-crean).
    
    Returns:
        True si los collectors están disponibles, False si hubo error.
    """
    global _collectors_initialized
    global _delete_total, _delete_batch_size, _delete_latency
    global _delete_partial_failures, _delete_errors
    
    if _collectors_initialized:
        return True
    
    try:
        _delete_total = get_or_create_counter(
            DELETE_TOTAL_NAME,
            "Total file delete operations",
            labelnames=LABELS_DELETE_TOTAL,
        )
        _delete_batch_size = get_or_create_histogram(
            DELETE_BATCH_SIZE_NAME,
            "Batch size of delete operations",
            labelnames=(),
        )
        _delete_latency = get_or_create_histogram(
            DELETE_LATENCY_NAME,
            "Latency of delete operations in seconds",
            labelnames=LABELS_LATENCY,
        )
        _delete_partial_failures = get_or_create_counter(
            DELETE_PARTIAL_FAILURES_NAME,
            "Delete operations with at least one failure in batch",
            labelnames=LABELS_PARTIAL,
        )
        _delete_errors = get_or_create_counter(
            DELETE_ERRORS_NAME,
            "Delete errors by HTTP status code",
            labelnames=LABELS_ERRORS,
        )
        
        _collectors_initialized = True
        _logger.info("files_delete_metrics_initialized")
        return True
    except Exception as e:
        _logger.warning(
            "delete_metrics_init_error: %s - metrics disabled",
            str(e),
        )
        return False


# ---------------------------------------------------------------------------
# Public API - Safe increment/observe functions (no exceptions)
# ---------------------------------------------------------------------------

def inc_delete_total(
    file_type: str = "input",
    op: str = "single_delete",
    result: str = "success",
) -> None:
    """
    Incrementa contador de operaciones delete.
    
    Args:
        file_type: "input" | "product"
        op: "single_delete" | "bulk_delete" | "cleanup_ghosts"
        result: "success" | "partial" | "failure"
    """
    try:
        if _ensure_collectors() and _delete_total:
            _delete_total.labels(
                file_type=file_type,
                op=op,
                result=result,
            ).inc()
    except Exception:
        pass  # Never break caller flow


def observe_batch_size(batch_size: int) -> None:
    """
    Registra el tamaño del batch en el histogram.
    
    Args:
        batch_size: Número de archivos en el batch
    """
    try:
        if _ensure_collectors() and _delete_batch_size:
            _delete_batch_size.observe(batch_size)
    except Exception:
        pass


def observe_delete_latency(
    latency_seconds: float,
    file_type: str = "input",
    op: str = "single_delete",
) -> None:
    """
    Registra la latencia de la operación delete.
    
    Args:
        latency_seconds: Latencia en segundos
        file_type: "input" | "product"
        op: "single_delete" | "bulk_delete" | "cleanup_ghosts"
    """
    try:
        if _ensure_collectors() and _delete_latency:
            _delete_latency.labels(
                file_type=file_type,
                op=op,
            ).observe(latency_seconds)
    except Exception:
        pass


def inc_partial_failure(
    file_type: str = "input",
    op: str = "bulk_delete",
) -> None:
    """
    Incrementa contador de operaciones con failures parciales.
    
    Args:
        file_type: "input" | "product"
        op: "bulk_delete" | "cleanup_ghosts"
    """
    try:
        if _ensure_collectors() and _delete_partial_failures:
            _delete_partial_failures.labels(
                file_type=file_type,
                op=op,
            ).inc()
    except Exception:
        pass


def inc_delete_error(
    file_type: str = "input",
    status_code: str = "500",
) -> None:
    """
    Incrementa contador de errores por status code.
    
    Args:
        file_type: "input" | "product"
        status_code: "404" | "409" | "500" | "503"
    """
    try:
        if _ensure_collectors() and _delete_errors:
            _delete_errors.labels(
                file_type=file_type,
                status_code=status_code,
            ).inc()
    except Exception:
        pass


__all__ = [
    "inc_delete_total",
    "observe_batch_size",
    "observe_delete_latency",
    "inc_partial_failure",
    "inc_delete_error",
    # Metric names for documentation
    "DELETE_TOTAL_NAME",
    "DELETE_BATCH_SIZE_NAME",
    "DELETE_LATENCY_NAME",
    "DELETE_PARTIAL_FAILURES_NAME",
    "DELETE_ERRORS_NAME",
]

# Fin del archivo backend/app/modules/files/metrics/collectors/delete_collectors.py
