# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_common.py

Common helper functions for PDF conversion shared between baseline and adaptive converters.
This is the **single place** that shapes PDF outputs into {text, tables, forms} structure.

Autor: DoxAI
Fecha: 05/09/2025
"""

from typing import Dict, List, Union, Any
# TODO: Implementar módulo RAG completo
# from app.modules.rag.utils.text_structure_service import enhanced_elements_to_text_with_titles
# from app.modules.rag.utils.table_reconstruction_service import reconstruct_table_from_raw
# from app.modules.rag.utils.form_detection_service import detect_form_declarations
# from app.modules.rag.utils.ocr_cleaning_service import clean_ocr_text


def elements_to_outputs(elements: List[Any]) -> Dict[str, Union[str, List]]:
    """
    Convert Unstructured elements into standardized PDF outputs.
    
    This is the canonical function that transforms parsed PDF elements into the 
    standard {text, tables, forms} structure used throughout the RAG pipeline.
    
    Args:
        elements: List of Unstructured-like elements with .text and .category attributes
        
    Returns:
        Dict with keys:
        - "text": str - structured text with hierarchical titles
        - "tables": List[dict] - reconstructed tables with metadata
        - "forms": List[dict] - detected form declarations and fillable fields
    """
    # Extract structured text with hierarchical titles
    text = enhanced_elements_to_text_with_titles(elements)
    
    # Process each element for tables and forms
    tables = []
    forms = []
    
    for i, el in enumerate(elements):
        raw_text = clean_ocr_text(el.text.strip())
        
        # Detect forms in text elements
        if el.category == "Text":
            detected_forms = detect_form_declarations(raw_text)
            if detected_forms:
                forms.extend(detected_forms)
        
        # Process table-like elements
        is_table_like = (
            el.category == "Table" or 
            (el.category == "Text" and len(raw_text.splitlines()) >= 3)
        )
        
        if is_table_like:
            reconstruction = reconstruct_table_from_raw(raw_text)
            rows = reconstruction.get("rows", [])
            
            if not rows:
                continue
            
            # Filter single-row tables without relevant content
            if len(rows) == 1:
                flat = " ".join(c.lower() for c in rows[0])
                if not any(kw in flat for kw in ["firma", "importe", "precio", "total", "documento", "actividad"]):
                    continue
            
            table_obj = {
                "source_block": i,
                "type": reconstruction.get("type", "informativa"),
                "confidence": reconstruction.get("confidence", 0.5),
                "n_rows": len(rows),
                "n_cols": len(rows[0]) if rows else 0,
                "rows": rows,
                "raw": raw_text
            }
            
            tables.append(table_obj)
            
            # Detect forms in table cells
            for row in rows:
                for cell in row:
                    cell_forms = detect_form_declarations(cell)
                    if cell_forms:
                        forms.extend(cell_forms)
    
    return {
        "text": text,
        "tables": tables,
        "forms": forms
    }






