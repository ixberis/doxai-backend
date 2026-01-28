# -*- coding: utf-8 -*-
"""
backend/app/observability/metrics_init.py

Inicialización de todos los collectors Prometheus al startup.

Este módulo fuerza el registro de los collectors (Counter, Histogram, Gauge)
en el REGISTRY de Prometheus para que sus familias (# HELP, # TYPE) aparezcan
en /metrics desde el inicio.

Las series con labels aparecerán cuando haya actividad real (no se pre-crean).

Autor: DoxAI
Fecha: 2026-01-24
Updated: 2026-01-25 - Robust error logging with exc_info, registry verification
"""
from __future__ import annotations

import logging

_logger = logging.getLogger("observability.metrics_init")


def get_metrics_registry():
    """
    Obtiene el registry canónico usado por /metrics.
    
    SSOT: Importa desde app.observability.prom para usar exactamente
    el mismo registry que el endpoint /metrics.
    
    Returns:
        El registry que usa /metrics (multiprocess-aware).
    """
    from app.observability.prom import _get_metrics_registry
    return _get_metrics_registry()


def _get_registered_family_names() -> set:
    """
    Obtiene los nombres de familias registradas usando API pública.
    
    Usa REGISTRY.collect() (API pública) en lugar de _names_to_collectors.
    
    Returns:
        Set con nombres de familias de métricas.
    """
    try:
        registry = get_metrics_registry()
        return {metric.name for metric in registry.collect()}
    except Exception as e:
        _logger.error("metrics_get_family_names_error: %s", str(e), exc_info=True)
        return set()


def _verify_registry() -> dict:
    """
    Verifica qué métricas están registradas en el REGISTRY de Prometheus.
    
    IMPORTANTE: prometheus_client almacena Counters sin sufijo "_total" 
    en el registry interno. Por ejemplo, "files_delete_total" se registra
    como "files_delete". El sufijo se añade solo al exportar con generate_latest().
    
    Por tanto, esta función verifica los nombres BASE de las familias.
    
    Returns:
        dict con flags indicando presencia de cada familia de métricas.
    """
    try:
        family_names = _get_registered_family_names()
        
        # Use base names (no _total suffix for Counters)
        return {
            "has_files_delete": "files_delete" in family_names,
            "has_files_delete_latency_seconds": "files_delete_latency_seconds" in family_names,
            "has_touch_debounced_allowed": "touch_debounced_allowed" in family_names,
            "has_touch_debounced_skipped": "touch_debounced_skipped" in family_names,
            "has_doxai_ghost_files_count": "doxai_ghost_files_count" in family_names,
            "has_projects_lifecycle_requests": "projects_lifecycle_requests" in family_names,
            "has_projects_lifecycle_latency_seconds": "projects_lifecycle_latency_seconds" in family_names,
        }
    except Exception as e:
        _logger.error("metrics_registry_verify_error: %s", str(e), exc_info=True)
        return {}


def initialize_all_metrics() -> dict:
    """
    Inicializa todos los collectors Prometheus de forma temprana.
    
    Registra las familias de métricas (Counter, Histogram, Gauge) en el REGISTRY.
    Las series con labels aparecen cuando hay actividad real.
    
    Returns:
        dict con el estado de inicialización de cada collector.
    """
    results = {
        "files_delete": False,
        "touch_debounce": False,
        "db_metrics": False,
        "projects_lifecycle": False,
    }
    
    # ─────────────────────────────────────────────────────────────────────────
    # 1. Files Delete Collectors
    # ─────────────────────────────────────────────────────────────────────────
    try:
        from app.modules.files.metrics.collectors.delete_collectors import (
            _ensure_collectors as ensure_delete_collectors,
        )
        results["files_delete"] = ensure_delete_collectors()
        
        if results["files_delete"]:
            _logger.info("metrics_init: files_delete collectors registered ✓")
        else:
            _logger.error(
                "metrics_init: files_delete collectors returned False",
                exc_info=False,
            )
    except ImportError as ie:
        _logger.error(
            "metrics_init: files_delete IMPORT FAILED: %s",
            str(ie),
            exc_info=True,
        )
    except Exception as e:
        _logger.error(
            "metrics_init: files_delete INIT FAILED: %s",
            str(e),
            exc_info=True,
        )
    
    # ─────────────────────────────────────────────────────────────────────────
    # 2. Touch Debounce Collectors
    # ─────────────────────────────────────────────────────────────────────────
    try:
        from app.modules.projects.metrics.collectors.touch_debounce_collectors import (
            _ensure_counters as ensure_touch_counters,
        )
        results["touch_debounce"] = ensure_touch_counters()
        
        if results["touch_debounce"]:
            _logger.info("metrics_init: touch_debounce collectors registered ✓")
        else:
            _logger.error(
                "metrics_init: touch_debounce collectors returned False",
                exc_info=False,
            )
    except ImportError as ie:
        _logger.error(
            "metrics_init: touch_debounce IMPORT FAILED: %s",
            str(ie),
            exc_info=True,
        )
    except Exception as e:
        _logger.error(
            "metrics_init: touch_debounce INIT FAILED: %s",
            str(e),
            exc_info=True,
        )
    
    # ─────────────────────────────────────────────────────────────────────────
    # 3. DB Metrics Collector (gauges for ghost_files, storage_delta, etc.)
    # ─────────────────────────────────────────────────────────────────────────
    try:
        from app.shared.observability.db_metrics_collector import (
            get_db_metrics_collector,
        )
        collector = get_db_metrics_collector()
        results["db_metrics"] = collector._ensure_metrics()
        
        if results["db_metrics"]:
            _logger.info("metrics_init: db_metrics collector registered ✓")
        else:
            _logger.error(
                "metrics_init: db_metrics collector returned False",
                exc_info=False,
            )
    except ImportError as ie:
        _logger.error(
            "metrics_init: db_metrics IMPORT FAILED: %s",
            str(ie),
            exc_info=True,
        )
    except Exception as e:
        _logger.error(
            "metrics_init: db_metrics INIT FAILED: %s",
            str(e),
            exc_info=True,
        )
    
    # ─────────────────────────────────────────────────────────────────────────
    # 4. Projects Lifecycle Collectors
    # ─────────────────────────────────────────────────────────────────────────
    try:
        from app.modules.projects.metrics.collectors.lifecycle_collectors import (
            _ensure_collectors as ensure_lifecycle_collectors,
        )
        results["projects_lifecycle"] = ensure_lifecycle_collectors()
        
        if results["projects_lifecycle"]:
            _logger.info("metrics_init: projects_lifecycle collectors registered ✓")
        else:
            _logger.error(
                "metrics_init: projects_lifecycle collectors returned False",
                exc_info=False,
            )
    except ImportError as ie:
        _logger.error(
            "metrics_init: projects_lifecycle IMPORT FAILED: %s",
            str(ie),
            exc_info=True,
        )
    except Exception as e:
        _logger.error(
            "metrics_init: projects_lifecycle INIT FAILED: %s",
            str(e),
            exc_info=True,
        )
    
    # ─────────────────────────────────────────────────────────────────────────
    # Summary log
    # ─────────────────────────────────────────────────────────────────────────
    _logger.info(
        "metrics_init_summary: files_delete=%s touch_debounce=%s db_metrics=%s projects_lifecycle=%s",
        results["files_delete"],
        results["touch_debounce"],
        results["db_metrics"],
        results["projects_lifecycle"],
    )
    
    # ─────────────────────────────────────────────────────────────────────────
    # Registry verification (post-init check)
    # Uses base names (no _total suffix for Counters in registry)
    # ─────────────────────────────────────────────────────────────────────────
    registry_check = _verify_registry()
    _logger.info(
        "metrics_registry_check: has_files_delete=%s has_touch_debounced_allowed=%s "
        "has_files_delete_latency_seconds=%s has_doxai_ghost_files_count=%s "
        "has_projects_lifecycle_requests=%s has_projects_lifecycle_latency_seconds=%s",
        registry_check.get("has_files_delete", False),
        registry_check.get("has_touch_debounced_allowed", False),
        registry_check.get("has_files_delete_latency_seconds", False),
        registry_check.get("has_doxai_ghost_files_count", False),
        registry_check.get("has_projects_lifecycle_requests", False),
        registry_check.get("has_projects_lifecycle_latency_seconds", False),
    )
    
    return results


__all__ = ["initialize_all_metrics", "_verify_registry", "get_metrics_registry", "_get_registered_family_names"]
