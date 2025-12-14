
# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/plain_text_loader.py

Carga segura de archivos de texto plano (.txt) utilizando Unstructured.

- Utiliza la librería `unstructured` para obtener bloques semánticos desde archivos .txt.
- Extrae títulos, listas, párrafos o texto continuo como elementos independientes.
- Devuelve el contenido como string limpio, concatenado para el pipeline RAG.

Autor: Ixchel Beristain
Última revisión: 22/07/2025
"""

from typing import Optional, Callable, Dict
# TODO: Implementar módulo RAG completo
# from app.modules.rag.utils.unstructured_parser_service import parse_with_unstructured, elements_to_text


def load_plain_text(
    file_path: str,
    progress_cb: Optional[Callable[[str, float, Optional[Dict]], None]] = None,
    job_id: Optional[str] = None
) -> Optional[str]:
    """
    Carga el contenido completo de un archivo .txt estructurado por bloques.
    
    Args:
        file_path: Ruta absoluta del archivo
        progress_cb: Callback opcional para reporte de progreso
        job_id: ID opcional del job para logging contextual
    
    Returns:
        str | None: Contenido estructurado o None si falla
    """
    if progress_cb:
        progress_cb("loading", 0.1, {"message": "Cargando archivo de texto"})
    
    elements = parse_with_unstructured(file_path)
    
    if progress_cb:
        progress_cb("completed", 0.95, {
            "message": "Carga completada", 
            "elements_count": len(elements) if elements else 0
        })
    
    return elements_to_text(elements) if elements else None
# Fin del archivo plain_text_loader.py







