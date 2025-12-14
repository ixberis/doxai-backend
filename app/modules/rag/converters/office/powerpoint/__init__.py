# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/common_office_helpers.py

Helpers comunes para convertidores de documentos tipo office (Excel, PowerPoint, etc.)
que utilizan el pipeline de unstructured para extraer contenido estructurado.

Funcionalidades:
- Pipeline común para procesamiento de elementos unstructured
- Extracción de tablas y formularios con lógica compartida
- Limpieza OCR y detección de formularios reutilizable

Autor: Ixchel Beristain
Última revisión: 01/08/2025
"""

import os
from typing import Optional, Union, List, Dict, Callable, Any
from dataclasses import dataclass

# TODO: Implementar módulo RAG completo
# from app.modules.rag.utils.unstructured_parser_service import parse_with_unstructured
# from app.modules.rag.utils.text_structure_service import enhanced_elements_to_text_with_titles
# from app.modules.rag.utils.ocr_cleaning_service import clean_ocr_text
# from app.modules.rag.utils.table_reconstruction_service import reconstruct_table_from_raw
# from app.modules.rag.utils.form_detection_service import detect_form_declarations


@dataclass
class ConvertResult:
    """Resultado estructurado de conversión de documento office."""
    text: str
    tables: List[Dict]
    forms: List[Dict]


def process_office_document(
    file_path: str,
    *,
    legacy_extensions: List[str],
    legacy_converter: Callable[[str], Optional[str]],
    processing_message: str = "🔍 Procesando documento con Unstructured"
) -> Optional[ConvertResult]:
    """
    Pipeline común para procesamiento de documentos office usando unstructured.
    
    Args:
        file_path: Ruta del archivo a procesar
        legacy_extensions: Lista de extensiones que requieren conversión (ej: [".xls", ".ods"])
        legacy_converter: Función para convertir formatos legacy
        processing_message: Mensaje personalizado para logs
        
    Returns:
        ConvertResult con texto, tablas y formularios extraídos, o None si hay error
    """
    ext = os.path.splitext(file_path)[1].lower()

    # Convertir archivos legacy si es necesario
    if ext in legacy_extensions:
        file_path = legacy_converter(file_path)
        if not file_path:
            print("❌ Error al convertir archivo legacy")
            return None

    print(f"{processing_message}: {file_path}")
    elements = parse_with_unstructured(file_path)

    if not elements:
        print("❌ No se pudieron extraer bloques con Unstructured.")
        return None

    print(f"✅ Bloques detectados: {len(elements)}")
    
    # Extraer texto estructurado
    text = enhanced_elements_to_text_with_titles(elements)
    tables = []
    forms = []

    # Procesar cada elemento para extraer tablas y formularios
    for i, element in enumerate(elements):
        raw = clean_ocr_text(element.text.strip())

        # Detectar y reconstruir tablas
        if element.category == "Table" or (element.category == "Text" and len(raw.splitlines()) >= 3):
            reconstruction = reconstruct_table_from_raw(raw)
            rows = reconstruction.get("rows", [])
            if not rows:
                continue

            tables.append({
                "source_block": i,
                "type": reconstruction.get("type", "informativa"),
                "confidence": reconstruction.get("confidence", 0.5),
                "n_rows": len(rows),
                "n_cols": len(rows[0]) if rows else 0,
                "rows": rows,
                "raw": raw
            })

            # Detectar formularios en celdas de tabla
            for row in rows:
                for cell in row:
                    detected = detect_form_declarations(cell)
                    if detected:
                        forms.extend(detected)

        # Detectar formularios en texto plano
        elif element.category == "Text":
            detected = detect_form_declarations(raw)
            if detected:
                forms.extend(detected)

    return ConvertResult(
        text=text,
        tables=tables,
        forms=forms
    )







