# -*- coding: utf-8 -*-
"""
backend/app/observability/metrics_init.py

Inicialización de todos los collectors Prometheus al startup.

Este módulo fuerza la inicialización lazy de todos los collectors para que
sus métricas aparezcan en /metrics desde el inicio, incluso si no han sido
invocados todavía.

Problema resuelto:
- Los collectors usan `_ensure_*()` lazy que solo registra métricas cuando
  se llama `inc_*()` o `observe_*()` por primera vez.
- Prometheus scrape puede no ver métricas hasta que haya actividad real.
- Este módulo fuerza la inicialización temprana.

Autor: DoxAI
Fecha: 2026-01-24
"""
from __future__ import annotations

import logging

_logger = logging.getLogger("observability.metrics_init")


def initialize_all_metrics() -> dict:
    """
    Inicializa todos los collectors Prometheus de forma temprana.
    
    Esto registra todas las métricas en el REGISTRY de Prometheus incluso
    antes de que haya actividad real, permitiendo que /metrics las liste
    desde el primer scrape.
    
    IMPORTANTE: Los collectors ahora inicializan cada label combination con
    valor 0, lo que hace que las métricas aparezcan inmediatamente en /metrics.
    
    Returns:
        dict con el estado de inicialización de cada collector.
    """
    results = {
        "files_delete": False,
        "touch_debounce": False,
        "db_metrics": False,
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
            _logger.info("metrics_init: files_delete collectors initialized ✓")
        else:
            _logger.warning("metrics_init: files_delete collectors returned False")
    except Exception as e:
        _logger.warning(f"metrics_init: files_delete failed: {e}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 2. Touch Debounce Collectors
    # ─────────────────────────────────────────────────────────────────────────
    try:
        from app.modules.projects.metrics.collectors.touch_debounce_collectors import (
            _ensure_counters as ensure_touch_counters,
        )
        results["touch_debounce"] = ensure_touch_counters()
        if results["touch_debounce"]:
            _logger.info("metrics_init: touch_debounce collectors initialized ✓")
        else:
            _logger.warning("metrics_init: touch_debounce collectors returned False")
    except Exception as e:
        _logger.warning(f"metrics_init: touch_debounce failed: {e}")
    
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
            _logger.info("metrics_init: db_metrics collector initialized ✓")
        else:
            _logger.warning("metrics_init: db_metrics collector returned False")
    except Exception as e:
        _logger.warning(f"metrics_init: db_metrics failed: {e}")
    
    # Summary log
    success_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    _logger.info(
        "metrics_init_complete: %d/%d collectors initialized",
        success_count,
        total_count,
    )
    
    return results


__all__ = ["initialize_all_metrics"]
