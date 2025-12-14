
# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/excel_converter.py

Conversión de archivos de hojas de cálculo (.xlsx, .xls, .csv, .ods) a texto estructurado para el pipeline RAG.

Funcionalidades:
- Convierte archivos .xls y .ods (legacy) a .xlsx mediante LibreOffice (soffice).
- Utiliza la librería `unstructured` para extraer contenido tabular y semántico.
- Aplica limpieza OCR defensiva (`clean_ocr_text`) para mejorar calidad textual.
- Reconstruye tablas a partir de bloques tabulares y las clasifica como 'informativa' o 'formulario'.
- Detecta formularios tipo declaración en bloques de texto o celdas.
- Retorna un objeto estructurado con campos `text`, `tables` y `forms`.

Autor: Ixchel Beristain
Última revisión: 01/08/2025
"""

import os
from typing import Optional, Union, List, Dict, Callable

from .excel_legacy_converter import convert_xls_to_xlsx
from .common_office_helpers import process_office_document


def convert_excel_to_text(
    file_path: str,
    progress_cb: Optional[Callable[[str, float, Optional[Dict]], None]] = None,
    job_id: Optional[str] = None
) -> Optional[Dict[str, Union[str, List]]]:
    """
    Convierte archivos de hojas de cálculo (.xlsx, .xls, .csv, .ods) a texto estructurado.
    
    Args:
        file_path: Ruta del archivo de Excel/hoja de cálculo
        progress_cb: Callback opcional para reporte de progreso (stage, percent, meta)
        job_id: ID opcional del job para logging contextual
    
    Returns:
        Dict con 'text', 'tables', 'forms' o None si falla la conversión
    """
    if progress_cb:
        progress_cb("preparing", 0.05, {"message": "Iniciando conversión Excel"})
    
    if progress_cb:
        progress_cb("processing", 0.3, {"message": "Procesando contenido del archivo"})
    
    result = process_office_document(
        file_path,
        legacy_extensions=[".xls", ".ods"],
        legacy_converter=convert_xls_to_xlsx,
        processing_message="🔍 Procesando archivo Excel con Unstructured"
    )
    
    if not result:
        if progress_cb:
            progress_cb("error", 0.0, {"error": "Error procesando archivo Excel"})
        return None
        
    if progress_cb:
        progress_cb("completed", 0.95, {
            "message": "Conversión Excel completada",
            "text_length": len(result.text),
            "tables_count": len(result.tables),
            "forms_count": len(result.forms)
        })
        
    return {
        "text": result.text,
        "tables": result.tables,
        "forms": result.forms
    }
# Fin del archivo excel_converter.py






