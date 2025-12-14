# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_table_pdfplumber_extractor.py

Pure pdfplumber table extraction functionality.
Handles borderless table extraction with optimized settings.

Author: Ixchel Beristain Mendoza
Refactored: 28/09/2025
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
import logging

from app.shared.utils.pdf_resource_manager import PDFResourceTracker

logger = logging.getLogger(__name__)


def extract_tables_pdfplumber(
    pdf_path: Union[str, Path],
    pages: List[int],
    pdf_mgr: Optional[PDFResourceTracker] = None
) -> List[Dict[str, Any]]:
    """
    Extrae tablas usando pdfplumber (mejor para tablas sin bordes).
    
    Args:
        pdf_path: Ruta del archivo PDF
        pages: Lista de páginas a procesar
        pdf_mgr: Gestor de recursos PDF opcional
        
    Returns:
        Lista de diccionarios con datos de tabla normalizados
    """
    try:
        import pdfplumber
    except ImportError:
        logger.warning("⚠️ pdfplumber no disponible, usando fallback")
        return []
    
    if not pages:
        return []
    
    # Check if file exists before attempting to open
    pdf_path_obj = Path(pdf_path)
    if not pdf_path_obj.exists():
        logger.warning(f"PDF file does not exist: {pdf_path}")
        return []
    
    tables = []
    
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            # Register pdfplumber object for cleanup
            if pdf_mgr:
                pdf_mgr.register_pdfplumber_object(pdf)
                pdf_mgr.register_file(Path(pdf_path))
                
            for page_num in pages:
                if page_num <= len(pdf.pages):
                    page = pdf.pages[page_num - 1]  # pdfplumber usa índice 0
                    
                    # Configuración de extracción de tablas
                    table_settings = _get_table_extraction_settings()
                    page_tables = page.extract_tables(table_settings)
                    
                    for i, table_data in enumerate(page_tables or []):
                        if table_data and len(table_data) > 1:  # Al menos header + 1 fila
                            processed_table = _process_raw_table_data(
                                table_data, page_num, i
                            )
                            if processed_table:
                                tables.append(processed_table)
        
    except Exception as e:
        logger.error(f"❌ Error extrayendo con pdfplumber: {str(e)}")
    
    logger.info(f"🔍 pdfplumber extrajo {len(tables)} tablas de páginas {pages}")
    return tables


def _get_table_extraction_settings() -> Dict[str, Any]:
    """
    Configuración optimizada para extracción de tablas con pdfplumber.
    
    Returns:
        Diccionario con configuración de extracción
    """
    return {
        "vertical_strategy": "lines_strict",
        "horizontal_strategy": "lines_strict",
        "explicit_vertical_lines": [],
        "explicit_horizontal_lines": [],
        "snap_tolerance": 3,
        "join_tolerance": 3,
        "edge_min_length": 3,
        "min_words_vertical": 3,
        "min_words_horizontal": 1,
        "intersection_tolerance": 3,
        "text_tolerance": 3,
        "text_x_tolerance": 3,
        "text_y_tolerance": 3,
    }


def _process_raw_table_data(
    table_data: List[List[Any]], 
    page_num: int, 
    table_index: int
) -> Optional[Dict[str, Any]]:
    """
    Procesa datos crudos de tabla de pdfplumber en formato estructurado.
    
    Args:
        table_data: Datos crudos de tabla de pdfplumber
        page_num: Número de página
        table_index: Índice de tabla en la página
        
    Returns:
        Diccionario con tabla procesada o None si no es válida
    """
    # Limpiar y filtrar datos
    rows = []
    for row in table_data:
        if row and any(cell and str(cell).strip() for cell in row):
            clean_row = [str(cell or "").strip() for cell in row]
            rows.append(clean_row)
    
    if not rows:
        return None
    
    return {
        "table_id": f"pdfplumber_{page_num}_{table_index}",
        "extraction_method": "pdfplumber",
        "page": page_num,
        "confidence": 0.7,  # Confianza estimada para pdfplumber
        "rows": rows,
        "table_type": "borderless",
        "bbox": None,  # pdfplumber no proporciona bbox directo
        "parsing_report": {
            "page": page_num,
            "table_index": table_index,
            "original_rows": len(table_data),
            "cleaned_rows": len(rows)
        }
    }






