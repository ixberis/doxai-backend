# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_conversion_handler.py

PDF-specific conversion handling with proper import resolution.
Handles PDF conversion using the adaptive controller.

Author: Ixchel Beristáin Mendoza
Date: 28/09/2025 - Refactored from conversion_dispatcher.py
"""

from pathlib import Path
from typing import Dict, Any, Optional, Callable, Union, List
import logging

# TODO: Implementar módulo RAG completo
# from app.modules.rag.logging.job_logger import add_job_log
from .progress_adapter import ProgressCallbackAdapter
from .pdf_rasterizer_backend import get_preferred_rasterizer

logger = logging.getLogger(__name__)


class PDFConversionHandler:
    """
    Handles PDF conversion using the adaptive controller.
    Single responsibility: PDF conversion orchestration.
    """
    
    def __init__(self):
        self.logger = logger
    
    async def convert_pdf(
        self, 
        file_path: Path, 
        file_meta: Dict[str, Any],
        operation_id: str,
        job_id: Optional[str],
        cancel_cb: Optional[Callable],
        progress_cb: Optional[Callable]
    ) -> Dict[str, Union[str, List]]:
        """
        Convert PDF using adaptive controller with proper error handling.
        
        Args:
            file_path: Path to PDF file
            file_meta: File metadata from estimate_conversion_duration
            operation_id: ID for timeout/operation tracking  
            job_id: Optional job ID for logging
            cancel_cb: Optional cancellation callback
            progress_cb: Optional progress callback
            
        Returns:
            Dict with 'text', 'tables', 'forms' keys
            
        Raises:
            ValueError: If conversion fails
            ImportError: If PDF converter is not available
        """
        pages = file_meta.get("pages", 1)
        
        # Log rasterizer backend
        rasterizer = get_preferred_rasterizer()
        self.logger.info(f"🔄 Converting PDF with {pages} pages using adaptive controller")
        self.logger.info(f"⚙️ Raster backend: {rasterizer.value}")
        
        # Create progress adapter for PDF
        adapter = ProgressCallbackAdapter("pdf")
        progress_reporter = adapter.create_simple_progress_reporter(progress_cb, job_id)
        
        # Report conversion start
        progress_reporter.start()
        
        try:
            # REINTENTO AGRESIVO: Si es PDF escaneado problemático, intentar dos veces
            max_attempts = 2
            last_error = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    # Import PDF adaptive controller (FIX: correct import)
                    from .pdf_adaptive_controller import convert_pdf_adaptive
                    
                    if attempt > 1:
                        self.logger.warning(f"🔄 Reintento {attempt}/{max_attempts} con parámetros agresivos para PDF escaneado")
                        add_job_log(job_id, "warn", f"🔄 Reintentando conversión con OCR agresivo (intento {attempt}/{max_attempts})")
                        # TODO: En el futuro, pasar parámetros agresivos (dpi_override=360, psm_override=11)
                    
                    # Call adaptive PDF converter (async)
                    result = await convert_pdf_adaptive(
                        pdf_path=file_path,
                        job_id=job_id,
                        cancel_cb=cancel_cb,
                        progress_cb=progress_cb  # Pass original callback to adaptive controller
                    )
                    
                    if not result:
                        raise ValueError("PDF conversion returned None")
                    
                    # Si llegamos aquí, la conversión fue exitosa
                    break  # Salir del loop de reintentos
                    
                except ValueError as ve:
                    # Capturar errores de validación de PDF escaneado
                    last_error = ve
                    error_msg = str(ve)
                    
                    if "Scanned PDF OCR validation failed" in error_msg and attempt < max_attempts:
                        # Es un PDF escaneado que falló validación, reintentar
                        self.logger.warning(f"⚠️ Validación de PDF escaneado falló en intento {attempt}, reintentando...")
                        add_job_log(job_id, "warn", f"⚠️ Validación falló, reintentando con parámetros más agresivos...")
                        continue  # Reintentar
                    else:
                        # No reintentar si no es error de PDF escaneado o ya agotamos intentos
                        raise
                except Exception as e:
                    # Otros errores no se reintentan
                    last_error = e
                    raise
            
            # Si salimos del loop sin break, significa que todos los intentos fallaron
            if last_error:
                self.logger.error(f"❌ Agotados {max_attempts} intentos de conversión")
                add_job_log(job_id, "error", f"❌ Conversión falló tras {max_attempts} intentos")
                raise last_error
            
            # Extract conversion metadata
            extraction_mode = result.get("extraction_mode", "unknown")
            no_text_extracted = result.get("no_text_extracted", False)
            md_size_bytes = result.get("md_size_bytes", 0)
            text_length = len(result.get("text", ""))
            
            # FASE 3: Log conversion results (handle ocr_required status)
            if result.get("status") == "ocr_required":
                # PDF escaneado detectado, OCR no disponible
                self.logger.warning(f"⚠️ PDF requires OCR but OCR is not available (scanned document)")
                add_job_log(job_id, "warning", f"⚠️ PDF escaneado detectado - se requiere Azure Document Intelligence")
            elif no_text_extracted:
                self.logger.warning(f"🚫 PDF converter: no_text_extracted=True (mode: {extraction_mode}, size: {md_size_bytes} bytes)")
                add_job_log(job_id, "warning", f"⚠️ PDF sin texto extraído tras OCR (modo: {extraction_mode})")
            else:
                self.logger.info(f"✅ PDF converter successful (mode: {extraction_mode}, size: {md_size_bytes} bytes, text: {text_length} chars)")
                add_job_log(job_id, "info", f"✅ PDF convertido exitosamente (modo: {extraction_mode}, {text_length} caracteres)")
            
            # Add OCR metrics if available
            if extraction_mode.startswith("ocr"):
                batches_processed = result.get("batches_processed", 0)
                if batches_processed > 0:
                    add_job_log(job_id, "info", f"📖 OCR procesó {batches_processed} lotes de páginas")
            
            # Report completion
            progress_reporter.complete(result)
            
            return result
            
        except ImportError as e:
            error_msg = f"PDF converter not available: {e}"
            self.logger.error(error_msg)
            add_job_log(job_id, "error", f"❌ Convertidor PDF no disponible: {str(e)}")
            progress_reporter.error(e)
            raise ValueError(error_msg) from e
            
        except Exception as e:
            self.logger.error(f"PDF conversion failed: {e}")
            add_job_log(job_id, "error", f"❌ Error en conversión PDF: {str(e)}")
            progress_reporter.error(e)
            raise






