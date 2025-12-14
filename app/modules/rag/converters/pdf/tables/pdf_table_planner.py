# -*- coding: utf-8 -*-
"""
PDF Table Planner - Handles table detection and hi-res page planning.
"""

from typing import List, Optional, Set, Dict, Any, Callable
import logging
import math

# TODO: Implementar módulo RAG completo
# from app.modules.rag.logging.job_logger import add_job_log
# from app.modules.rag.utils.timeout_manager import begin_phase, end_phase, get_time_remaining, execute_with_circuit_breaker
# from app.modules.rag.utils.table_detection import detect_table_pages
from .pdf_conversion_config import get_settings, should_force_all_pages_hi_res, get_hi_res_max_pages

logger = logging.getLogger(__name__)


def detect_and_plan_table_pages(
    elements_fast: List,
    pages_seen: Set[int],
    operation_id: str,
    strict_table_mode: bool,
    job_id: Optional[str] = None,
    progress_cb: Optional[Callable[[str, float, Optional[Dict[str, Any]]], None]] = None,
) -> Set[int]:
    """
    Detecta páginas con tablas y planifica procesamiento hi_res.
    
    Returns:
        Set de páginas que requieren procesamiento hi_res
    """
    settings = get_settings()
    table_pages = set()
    
    # Cargar modelo tablas si es necesario
    if strict_table_mode or settings.DOXAI_CONVERT_STRATEGY in ("adaptive", "hi_res"):
        _load_table_model(job_id)
        
        table_pages = detect_table_pages(elements_fast) or set()
        
        # Forzar hi_res en todas las páginas si está configurado
        if should_force_all_pages_hi_res():
            table_pages = pages_seen or set()
            add_job_log(job_id, "info", 
                       f"🔧 Forzado hi_res en todas las páginas ({len(table_pages)}) por estrategia/flag")
    
    if not table_pages:
        add_job_log(job_id, "info", "✅ No se detectaron tablas → solo elementos fast")
    
    return table_pages


def plan_hi_res_processing(
    table_pages: Set[int],
    operation_id: str,
    hi_res_timeout: int,
    job_id: Optional[str] = None,
    progress_cb: Optional[Callable[[str, float, Optional[Dict[str, Any]]], None]] = None,
) -> List[int]:
    """
    Planifica qué páginas procesar con hi_res basado en tiempo y límites.
    
    Returns:
        Lista de páginas planificadas para hi_res
    """
    begin_phase(operation_id, "hi_res_planning")

    # Respetar máximo de páginas hi_res desde settings
    hi_res_max = get_hi_res_max_pages()
    # Estimación conservadora por página (timeout + overhead 15%)
    per_page_budget = hi_res_timeout * 1.15

    # Ordenar páginas y aplicar límite duro por count
    sorted_candidates = sorted(table_pages)
    limited_by_count = sorted_candidates[:hi_res_max]

    # Limitar también por tiempo restante
    remaining = get_time_remaining(operation_id)
    # reservar 5s para merge y cierre
    reserved_tail = 5.0
    usable = max(0.0, remaining - reserved_tail)
    
    if per_page_budget <= 0:
        allowed_by_time = len(limited_by_count)
    else:
        allowed_by_time = int(math.floor(usable / per_page_budget))

    allowed = max(0, min(len(limited_by_count), allowed_by_time))
    planned_pages = limited_by_count[:allowed]

    if progress_cb:
        progress_cb(
            "converting:hi_res",
            0.05,
            {
                "candidate_pages": len(sorted_candidates),
                "max_pages": hi_res_max,
                "planned_pages": len(planned_pages),
                "remaining_sec": int(remaining),
            },
        )

    add_job_log(job_id, "info", f"🔍 Páginas hi_res planificadas: {planned_pages} "
                                f"(candidatas={len(sorted_candidates)}, max={hi_res_max}, "
                                f"per_page≈{per_page_budget:.1f}s, remaining≈{remaining:.1f}s)")

    end_phase(operation_id, "hi_res_planning")
    
    return planned_pages


def _load_table_model(job_id: Optional[str]):
    """Carga el modelo de tablas usando circuit breaker."""
    def _load_table():
        from app.shared.core.resource_cache import ensure_table_model_loaded
        ensure_table_model_loaded()
        return True

    execute_with_circuit_breaker("table_model_loading", _load_table)
    add_job_log(job_id, "info", "🔁 Table Agent disponible (singleton)")


def check_time_budget_for_hi_res(
    planned_pages: List[int],
    operation_id: str,
    per_page_budget: float,
    job_id: Optional[str] = None,
    progress_cb: Optional[Callable[[str, float, Optional[Dict[str, Any]]], None]] = None,
) -> bool:
    """
    Verifica si hay tiempo suficiente para procesamiento hi_res.
    
    Returns:
        True si hay tiempo suficiente, False en caso contrario
    """
    if not planned_pages:
        return False
    
    remaining_time = get_time_remaining(operation_id)
    
    if remaining_time < per_page_budget:
        logger.warning(f"⏱️ Tiempo insuficiente para hi_res ({remaining_time:.1f}s < {per_page_budget:.1f}s)")
        if progress_cb:
            progress_cb("converting:fast", 1.0, {"message": "Tiempo insuficiente para hi_res"})
        return False
    
    return True






