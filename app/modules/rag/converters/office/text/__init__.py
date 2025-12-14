
# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pptx_converter.py

Conversión de presentaciones PowerPoint (.pptx, .ppt, .odp) a texto estructurado para el pipeline RAG.

Funcionalidades:
- Convierte archivos .ppt (legacy) y .odp (OpenDocument Presentation) a .pptx utilizando LibreOffice (soffice).
- Extrae contenido slide por slide usando la librería `unstructured`.
- Aplica limpieza OCR defensiva (`clean_ocr_text`) para mejorar calidad textual.
- Preserva jerarquía documental con títulos y subtítulos.
- Detecta y reconstruye tablas densas, clasificándolas como 'informativa' o 'formulario'.
- Detecta formularios tipo declaración en el contenido textual.
- Devuelve un objeto con `text`, `tables` y `forms` para el pipeline RAG.

Autor: Ixchel Beristain
Última revisión: 01/08/2025
"""

import os
from typing import Optional, Union, List, Dict, Callable

from .ppt_legacy_converter import convert_ppt_to_pptx
from .common_office_helpers import process_office_document


def convert_pptx_to_text(
    file_path: str,
    progress_cb: Optional[Callable[[str, float, Optional[Dict]], None]] = None,
    job_id: Optional[str] = None
) -> Optional[Dict[str, Union[str, List]]]:
    """
    Convierte presentaciones PowerPoint (.pptx, .ppt, .odp) a texto estructurado.
    
    Args:
        file_path: Ruta del archivo PowerPoint
        progress_cb: Callback opcional para reporte de progreso (stage, percent, meta)
        job_id: ID opcional del job para logging contextual
    
    Returns:
        Dict con 'text', 'tables', 'forms' o None si falla la conversión
    """
    if progress_cb:
        progress_cb("preparing", 0.05, {"message": "Iniciando conversión PowerPoint"})
    
    if progress_cb:
        progress_cb("processing", 0.3, {"message": "Procesando contenido del archivo"})
    
    result = process_office_document(
        file_path,
        legacy_extensions=[".ppt", ".odp"],
        legacy_converter=convert_ppt_to_pptx,
        processing_message="🔍 Procesando archivo PowerPoint con Unstructured"
    )
    
    if not result:
        if progress_cb:
            progress_cb("error", 0.0, {"error": "Error procesando archivo PowerPoint"})
        return None
        
    if progress_cb:
        progress_cb("completed", 0.95, {
            "message": "Conversión PowerPoint completada",
            "text_length": len(result.text),
            "tables_count": len(result.tables),
            "forms_count": len(result.forms)
        })
        
    return {
        "text": result.text,
        "tables": result.tables,
        "forms": result.forms
    }
# Fin del archivo pptx_converter.py







