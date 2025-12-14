# -*- coding: utf-8 -*-
"""
PDF Element Merger - Handles merging of fast and hi-res elements.
"""

from typing import List, Optional
import logging

# TODO: Implementar módulo RAG completo
# from app.modules.rag.logging.job_logger import add_job_log
# from app.modules.rag.utils.timeout_manager import begin_phase, end_phase

logger = logging.getLogger(__name__)


def merge_elements(
    elements_fast: List, 
    elements_hi: Optional[List],
    operation_id: str,
    job_id: Optional[str] = None
) -> List:
    """
    Mezcla elementos fast y hi_res, reemplazando páginas de fast con las de hi_res.

    Args:
        elements_fast: Elementos obtenidos con strategy="fast"
        elements_hi: Elementos obtenidos con strategy="hi_res" (puede ser None)
        operation_id: ID de operación para tracking
        job_id: ID del job para logging

    Returns:
        Lista fusionada de elementos
    """
    begin_phase(operation_id, "merge")
    
    if not elements_hi:
        end_phase(operation_id, "merge")
        return elements_fast

    # Conjunto de páginas presentes en hi_res
    hi_res_pages = set()
    for el in elements_hi:
        page = getattr(el, "metadata", None) and getattr(el.metadata, "page_number", None)
        if page:
            hi_res_pages.add(page)

    # Mantener de fast SOLO las páginas NO reemplazadas por hi_res
    filtered_fast = []
    for el in elements_fast:
        page = getattr(el, "metadata", None) and getattr(el.metadata, "page_number", None)
        if page not in hi_res_pages:
            filtered_fast.append(el)

    # Combinar y ordenar
    all_elements = filtered_fast + elements_hi
    all_elements.sort(key=_get_sort_key)

    logger.info(
        "🔗 Elementos fusionados: fast_kept=%d + hi_res=%d = total=%d",
        len(filtered_fast), len(elements_hi), len(all_elements)
    )
    
    add_job_log(job_id, "info", f"🔗 Elementos fusionados: total={len(all_elements)} "
                                f"(fast_no_replaced={len(filtered_fast)}, hi_res={len(elements_hi)})")
    
    end_phase(operation_id, "merge")
    return all_elements


def _get_sort_key(el):
    """Genera clave de ordenamiento para elementos basada en página y coordenadas."""
    page = getattr(el, "metadata", None) and getattr(el.metadata, "page_number", None) or 0
    coords = getattr(el, "metadata", None) and getattr(el.metadata, "coordinates", None)
    
    if coords and hasattr(coords, "points"):
        try:
            # Orden vertical (top→bottom): y grande arriba en muchos backends
            y_coord = coords.points[0][1] if coords.points else 0
            return (page, -y_coord)
        except Exception:
            pass
    
    return (page, 0)


def create_fallback_result(pdf_path, job_id: Optional[str] = None):
    """Crea resultado de fallback usando solo estrategia fast."""
    from unstructured.partition.pdf import partition_pdf
    # TODO: Implementar módulo RAG completo
    # from app.modules.rag.converters.pdf_common import elements_to_outputs
    
    # Temporalmente usar None hasta que RAG esté implementado
    logger.warning("⚠️ RAG module not implemented - fallback result unavailable")
    return None
    
    # add_job_log(job_id, "warn", "🔄 Fallback a fast simple...")
    
    elements_fallback = partition_pdf(
        filename=str(pdf_path),
        strategy="fast",
        include_page_breaks=True,
        languages=["spa"],
        detect_language_per_page=False,
        extract_images_in_pdf=False,
    )
    
    return elements_to_outputs(elements_fallback or [])






