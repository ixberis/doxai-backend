# -*- coding: utf-8 -*-
"""
PDF Fast Processor - Handles fast strategy PDF processing.
"""

from pathlib import Path
from typing import List, Optional, Callable, Dict, Any, Set
import logging

from unstructured.partition.pdf import partition_pdf
# TODO: Implementar módulo RAG completo
# from app.modules.rag.logging.job_logger import add_job_log
# from app.modules.rag.utils.timeout_manager import begin_phase, end_phase, add_checkpoint
from .pdf_conversion_config import get_target_element_count, get_element_count_warning_range

logger = logging.getLogger(__name__)


def partition_fast_single_page(filename: str, page: int, languages: List[str]):
    """Ejecuta partition_pdf fast para una página específica."""
    return partition_pdf(
        filename=filename,
        strategy="fast",
        pages=[page],
        languages=languages,
        infer_table_structure=False,
        detect_language_per_page=False,
    )


def run_fast_pass_complete(
    pdf_path: Path,
    operation_id: str,
    job_id: Optional[str] = None,
    progress_cb: Optional[Callable[[str, float, Optional[Dict[str, Any]]], None]] = None,
) -> tuple[List, Set[int], int]:
    """
    Ejecuta la pasada fast completa del PDF.
    
    Returns:
        Tuple (elements_fast, pages_seen, total_pages)
    """
    begin_phase(operation_id, "fast_pass")
    
    if progress_cb:
        progress_cb("converting:fast", 0.05, None)

    add_job_log(job_id, "info", "⚡ Iniciando pasada fast completa")
    
    elements_fast = partition_pdf(
        filename=str(pdf_path),
        strategy="fast",
        include_page_breaks=True,
        languages=["spa"],
        detect_language_per_page=False,
        extract_images_in_pdf=False,
    )

    if not elements_fast:
        add_job_log(job_id, "warn", "⚠️ Primera pasada fast no devolvió elementos")
        elements_fast = []

    # Páginas presentes en fast (telemetría)
    pages_seen = set()
    for el in elements_fast:
        page = getattr(el, "metadata", None) and getattr(el.metadata, "page_number", None)
        if page:
            pages_seen.add(page)
    
    # Obtener número REAL de páginas del PDF usando PyMuPDF
    # Esto es crítico para PDFs escaneados donde pages_seen puede estar vacío
    total_pages = _get_real_page_count(pdf_path, len(pages_seen), job_id)

    if progress_cb:
        progress_cb("converting:fast", 0.85, {
            "fast_elements": len(elements_fast), 
            "total_pages": total_pages
        })
    
    add_job_log(job_id, "info", f"⚡ Fast pass: {len(elements_fast)} elementos en {total_pages} páginas")
    
    # Validate element count (conservative quality check)
    _validate_element_count(elements_fast, job_id)
    
    end_phase(operation_id, "fast_pass")
    add_checkpoint(operation_id, f"fast_done:{len(elements_fast)}")
    
    return elements_fast, pages_seen, total_pages


def _get_real_page_count(pdf_path: Path, pages_seen_count: int, job_id: Optional[str]) -> int:
    """
    Obtiene el número real de páginas del PDF usando PyMuPDF.
    
    Args:
        pdf_path: Ruta al archivo PDF
        pages_seen_count: Número de páginas detectadas en metadata (fallback)
        job_id: ID del job para logging
        
    Returns:
        Número real de páginas del PDF
    """
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(pdf_path))
        real_page_count = len(doc)
        doc.close()
        
        # Log si hay discrepancia (PDFs escaneados típicamente tienen pages_seen=0)
        if pages_seen_count != real_page_count:
            logger.info(f"📄 PDF tiene {real_page_count} páginas reales "
                       f"(metadata indicaba {pages_seen_count})")
            if pages_seen_count == 0:
                add_job_log(job_id, "info", 
                           f"📄 PDF escaneado: {real_page_count} páginas detectadas vía PyMuPDF")
        
        return real_page_count
        
    except ImportError:
        logger.warning("⚠️ PyMuPDF no disponible; usando conteo de metadata")
        return pages_seen_count or 1
    except Exception as e:
        logger.error(f"❌ Error obteniendo conteo de páginas PDF: {e}")
        return pages_seen_count or 1


def _validate_element_count(elements: List, job_id: Optional[str]):
    """Valida el conteo de elementos extraídos."""
    target_count = get_target_element_count()
    warning_range = get_element_count_warning_range()
    
    if not (warning_range[0] <= len(elements) <= warning_range[1]):
        logger.warning(f"⚠️ Element count {len(elements)} outside expected range {warning_range} (target ~{target_count})")
        add_job_log(job_id, "warn", f"Element count {len(elements)} may indicate quality issues")


def warmup_unstructured_models(operation_id: str):
    """Calienta los modelos de Unstructured si es necesario."""
    # TODO: Implementar módulo RAG completo
    # from app.modules.rag.utils.timeout_manager import execute_with_circuit_breaker
    
    logger.warning("⚠️ RAG module not implemented - model warmup unavailable")
    return
    
    def _warmup():
        from app.shared.core.resource_cache import warmup_unstructured
        from .pdf_conversion_config import get_settings
        settings = get_settings()
        warmup_unstructured(load_table_model=settings.DOXAI_PRELOAD_TABLE_MODEL)
        return True

    execute_with_circuit_breaker("pdf_adaptive_warmup", _warmup)







