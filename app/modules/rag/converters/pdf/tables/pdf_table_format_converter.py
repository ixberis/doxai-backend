# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_table_format_converter.py

Format conversion utilities for table data.
Converts between different table formats for pipeline compatibility.

Author: Ixchel Beristain Mendoza
Refactored: 28/09/2025
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


def convert_to_unstructured_format(specialized_tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convierte tablas del formato especializado al formato estándar de unstructured
    para compatibilidad con el pipeline existente.
    
    Args:
        specialized_tables: Lista de tablas en formato especializado
        
    Returns:
        Lista de tablas en formato compatible con unstructured
    """
    converted = []
    
    for table in specialized_tables:
        converted_table = _convert_single_table_to_unstructured(table)
        if converted_table:
            converted.append(converted_table)
    
    logger.info(f"🔄 Convertidas {len(converted)} tablas a formato unstructured")
    return converted


def _convert_single_table_to_unstructured(table: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Convierte una tabla individual al formato unstructured.
    
    Args:
        table: Tabla en formato especializado
        
    Returns:
        Tabla en formato unstructured o None si no es válida
    """
    rows = table.get("rows", [])
    if not rows:
        return None
    
    # Formato compatible con unstructured
    converted_table = {
        "rows": rows,
        "table_type": table.get("table_type", "extracted"),
        "page": table.get("page"),
        "extraction_confidence": table.get("confidence", 0.7),
        "extraction_method": table.get("extraction_method", "specialized"),
        "bbox": table.get("bbox"),
        "metadata": {
            "table_id": table.get("table_id"),
            "parsing_report": table.get("parsing_report", {}),
            "specialized_extraction": True
        }
    }
    
    return converted_table


def convert_from_unstructured_format(unstructured_tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convierte tablas del formato unstructured al formato especializado interno.
    
    Args:
        unstructured_tables: Lista de tablas en formato unstructured
        
    Returns:
        Lista de tablas en formato especializado
    """
    converted = []
    
    for table in unstructured_tables:
        converted_table = _convert_single_table_from_unstructured(table)
        if converted_table:
            converted.append(converted_table)
    
    logger.info(f"🔄 Convertidas {len(converted)} tablas desde formato unstructured")
    return converted


def _convert_single_table_from_unstructured(table: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Convierte una tabla individual desde formato unstructured.
    
    Args:
        table: Tabla en formato unstructured
        
    Returns:
        Tabla en formato especializado o None si no es válida
    """
    rows = table.get("rows", [])
    if not rows:
        return None
    
    metadata = table.get("metadata", {})
    
    # Formato especializado interno
    converted_table = {
        "table_id": metadata.get("table_id", f"unstructured_{id(table)}"),
        "extraction_method": table.get("extraction_method", "unstructured"),
        "page": table.get("page"),
        "confidence": table.get("extraction_confidence", 0.5),
        "rows": rows,
        "table_type": table.get("table_type", "extracted"),
        "bbox": table.get("bbox"),
        "parsing_report": metadata.get("parsing_report", {})
    }
    
    return converted_table


def validate_table_format(table: Dict[str, Any], format_type: str = "specialized") -> bool:
    """
    Valida que una tabla tenga el formato correcto.
    
    Args:
        table: Tabla a validar
        format_type: Tipo de formato esperado ("specialized" o "unstructured")
        
    Returns:
        True si el formato es válido
    """
    if not isinstance(table, dict):
        return False
    
    # Validaciones comunes
    if not table.get("rows") or not isinstance(table["rows"], list):
        return False
    
    if format_type == "specialized":
        return _validate_specialized_format(table)
    elif format_type == "unstructured":
        return _validate_unstructured_format(table)
    
    return False


def _validate_specialized_format(table: Dict[str, Any]) -> bool:
    """Valida formato especializado."""
    required_fields = ["table_id", "extraction_method", "page", "confidence"]
    return all(field in table for field in required_fields)


def _validate_unstructured_format(table: Dict[str, Any]) -> bool:
    """Valida formato unstructured."""
    required_fields = ["table_type", "page"]
    return all(field in table for field in required_fields)






