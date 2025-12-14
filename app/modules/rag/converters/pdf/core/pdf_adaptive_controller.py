# -*- coding: utf-8 -*-
"""
PDF Adaptive Controller - Main controller for adaptive PDF conversion.
Refactored from the original 471-line monolithic file.
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, Optional, List, Union, Callable
import logging
import time

# TODO: Implementar módulo RAG completo
# from app.modules.rag.converters.pdf_common import elements_to_outputs
# from app.modules.rag.logging.job_logger import add_job_log
# from app.modules.rag.converters.pdf_rasterizer_backend import get_preferred_rasterizer
# from app.modules.rag.utils.timeout_manager import (
    get_timeout_manager,
    register_global_operation,
    finish_global_operation,
    begin_phase,
    end_phase,
)

# Import refactored components
from .pdf_conversion_config import (
    get_settings, should_use_fast_strategy, should_process_hi_res,
    allow_partial_results, get_hi_res_timeout
)
from .pdf_fast_processor import run_fast_pass_complete, warmup_unstructured_models
from .pdf_table_planner import (
    detect_and_plan_table_pages, plan_hi_res_processing, 
    check_time_budget_for_hi_res
)
# ARCHIVED: OCR local modules moved to backend/archived/ocr_local/
# from .pdf_hires_processor import process_hi_res_pages
from .pdf_element_merger import merge_elements, create_fallback_result

logger = logging.getLogger(__name__)


async def convert_pdf_adaptive(
    pdf_path: Path,
    job_id: Optional[str] = None,
    strict_table_mode: Optional[bool] = None,
    cancel_cb: Optional[Callable[[], bool]] = None,
    progress_cb: Optional[Callable[[str, float, Optional[Dict[str, Any]]], None]] = None,
) -> Dict[str, Union[str, List]]:
    """
    Conversión adaptativa de PDF con telemetría y progreso granular, sensible
    al presupuesto de tiempo global. Devuelve parciales si el tiempo se agota.

    Args:
        pdf_path: Ruta del archivo PDF
        job_id: ID del job para logging y progreso
        strict_table_mode: Si True/False fuerza modo; si None, usa settings.DOXAI_STRICT_TABLE_MODE
        cancel_cb: Callback de cancelación (opcional)
        progress_cb: Callback de progreso (etiqueta, avance [0-1], meta dict)

    Returns:
        Dict con 'text', 'tables' y 'forms' extraídos.
    """
    settings = get_settings()
    if strict_table_mode is None:
        strict_table_mode = settings.DOXAI_STRICT_TABLE_MODE

    operation_id = f"pdf_conversion_{job_id or 'unknown'}"
    tm = get_timeout_manager()

    # Log rasterizer backend
    rasterizer = get_preferred_rasterizer()
    logger.info(f"⚙️ Raster backend seleccionado: {rasterizer.value}")

    # Registrar operación con presupuesto global actual
    total_budget = getattr(settings, "DOXAI_GLOBAL_CONVERSION_TIMEOUT", tm.config.global_conversion_timeout)
    register_global_operation(operation_id, timeout_seconds=int(total_budget))
    add_job_log(job_id, "info", f"🔄 Iniciando conversión PDF (adaptive, strict_table_mode={strict_table_mode}, budget={total_budget}s)")
    add_job_log(job_id, "info", f"⚙️ Raster backend: {rasterizer.value}")

    elements_fast: List = []
    # elements_hi removed - hi-res processor archived (FASE 5)
    
    try:
        # === PREPARACIÓN ===
        begin_phase(operation_id, "preparing")
        if progress_cb:
            progress_cb("preparing", 0.3, {"note": "Inicializando conversión PDF..."})

        warmup_unstructured_models(operation_id)
        end_phase(operation_id, "preparing")

        # === FAST PASS ===
        elements_fast, pages_seen, total_pages = run_fast_pass_complete(
            pdf_path, operation_id, job_id, progress_cb
        )

        # Si estrategia es 'fast', terminar aquí
        if should_use_fast_strategy():
            add_job_log(job_id, "info", "✅ Conversión completada con strategy=fast únicamente")
            if progress_cb:
                progress_cb("converting:fast", 1.0, None)
            result = elements_to_outputs(elements_fast)
            finish_global_operation(operation_id)
            return result

        # === FASE 3: DETECCIÓN TEMPRANA Y ROBUSTA DE PDF ESCANEADO ===
        # Estrategia multi-criterio para identificar PDFs escaneados con alta precisión
        total_text_length = sum(len(getattr(el, "text", "")) for el in elements_fast)
        avg_chars_per_page = total_text_length / max(total_pages, 1)
        
        # Criterios de detección (múltiples señales para mayor precisión)
        very_few_elements = len(elements_fast) < 50           # Señal fuerte: casi sin elementos
        few_elements = len(elements_fast) < 200               # Señal media: pocos elementos
        minimal_text = avg_chars_per_page < 50                # Señal fuerte: casi sin texto
        low_text = avg_chars_per_page < 100                   # Señal media: poco texto
        
        # Decisión robusta: 2+ señales fuertes OR 1 señal fuerte + 1 media
        is_scanned_pdf = (
            (very_few_elements and minimal_text) or           # Ambas señales fuertes
            (very_few_elements and low_text) or               # 1 fuerte + 1 media
            (few_elements and minimal_text)                   # 1 media + 1 fuerte
        )
        
        # Metadata enriquecido para debugging y logging
        scan_detection_metadata = {
            "is_scanned": is_scanned_pdf,
            "total_pages": total_pages,
            "elements_detected": len(elements_fast),
            "total_text_chars": total_text_length,
            "avg_chars_per_page": round(avg_chars_per_page, 1),
            "detection_signals": {
                "very_few_elements": very_few_elements,
                "few_elements": few_elements,
                "minimal_text": minimal_text,
                "low_text": low_text
            }
        }
        
        if is_scanned_pdf:
            # FASE 3+5: PDF escaneado detectado
            # OCR local archivado - siempre devolver OCR_REQUIRED
            from app.shared.config import settings as rag_settings
            ocr_enabled = rag_settings.ocr.enabled
            
            error_msg = (
                f"📷 PDF escaneado detectado. "
                f"Páginas: {total_pages}, elementos: {len(elements_fast)}, "
                f"texto total: {total_text_length} chars, promedio: {avg_chars_per_page:.1f} chars/pág. "
                f"OCR local archivado - se requiere Azure Document Intelligence para procesar."
            )
            logger.warning(f"⚠️ {error_msg}")
            add_job_log(job_id, "warn", f"⚠️ {error_msg}")
            add_job_log(job_id, "warn", "🚫 Archivo omitido: OCR_REQUIRED (OCR local archivado)")
            add_job_log(job_id, "info", f"📊 Señales de detección: {scan_detection_metadata['detection_signals']}")
            
            # FASE 3: Retornar resultado estructurado con metadata completo
            finish_global_operation(operation_id)
            return {
                "text": "",
                "tables": [],
                "forms": [],
                "status": "ocr_required",
                "reason": "Scanned PDF detected - OCR local archived, Azure Document Intelligence integration required",
                "skip_reason": "ocr_local_archived_scanned_pdf",  # Machine-readable reason
                "metadata": scan_detection_metadata
            }
        
        # === DETECCIÓN DE TABLAS (solo para PDFs no escaneados) ===
        table_pages = detect_and_plan_table_pages(
            elements_fast, pages_seen, operation_id, strict_table_mode, job_id, progress_cb
        )

        # FASE 5: Hi-res processor archivado - solo usar fast strategy
        # TODO: Implementar procesamiento hi-res con Azure Document Intelligence
        if table_pages:
            logger.info(f"ℹ️ {len(table_pages)} páginas con tablas detectadas, pero hi-res processor archivado")
            add_job_log(job_id, "info", 
                       f"ℹ️ {len(table_pages)} páginas con tablas - esperando Azure Document Intelligence")
        
        # Retornar solo resultados fast (no hay hi-res disponible)
        add_job_log(job_id, "info", "✅ Conversión completada con strategy=fast (hi-res archivado)")
        if progress_cb:
            progress_cb("converting:fast", 1.0, None)
        
        result = elements_to_outputs(elements_fast)

        add_job_log(job_id, "info",
                    f"📊 Conversión completada: tablas={len(result.get('tables', []))}, "
                    f"formularios={len(result.get('forms', []))}")
        
        # FASE 5: Validación de PDFs escaneados deshabilitada (OCR local archivado)
        # La detección de PDFs escaneados ya devuelve OCR_REQUIRED antes de llegar aquí
        
        finish_global_operation(operation_id)
        return result

    except InterruptedError as ie:
        logger.warning(f"🚫 Conversión cancelada: {ie}")
        # TODO: Implementar módulo RAG completo
        # add_job_log(job_id, "info", "🚫 Conversión PDF cancelada por el usuario")
        # from app.modules.rag.utils.progress_store import mark_job_cancelled
        # mark_job_cancelled(job_id)
        finish_global_operation(operation_id)
        raise ValueError("Job was cancelled during PDF conversion")

    except Exception as e:
        # Si hay elementos parciales y la config permite parciales, devuélvelos
        if elements_fast and allow_partial_results():
            logger.exception(f"⚠️ Error en conversión, devolviendo parciales: {e}")
            add_job_log(job_id, "warn", f"⚠️ Error en conversión, devolviendo parciales: {str(e)}")
            try:
                result = elements_to_outputs(elements_fast)
                finish_global_operation(operation_id)
                return result
            except Exception as merge_err:
                logger.error(f"❌ Error al consolidar parciales: {merge_err}")

        # Fallback de último recurso: fast simple
        logger.error(f"❌ Error en conversión adaptativa: {e}")
        add_job_log(job_id, "error", f"❌ Error en conversión adaptativa: {str(e)}")
        try:
            result = create_fallback_result(pdf_path, job_id)
            finish_global_operation(operation_id)
            return result
        finally:
            finish_global_operation(operation_id)


# Backward compatibility - export the timeout function
def get_hi_res_timeout() -> int:
    """Backward compatibility function."""
    from .pdf_conversion_config import get_hi_res_timeout as _get_timeout
    return _get_timeout()






