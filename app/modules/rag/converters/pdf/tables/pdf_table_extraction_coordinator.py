# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_table_extraction_coordinator.py

Coordinates specialized table extraction from PDFs.
Orchestrates multiple extraction methods and manages resources.

Author: Ixchel Beristain Mendoza
Refactored: 28/09/2025
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any, Union
import logging

from app.shared.utils.pdf_resource_manager import PDFResourceManager
from .pdf_table_pdfplumber_extractor import extract_tables_pdfplumber

logger = logging.getLogger(__name__)


def _get_settings():
    """Helper para acceder a settings con import lazy."""
    from app.shared.config import settings
    return settings


def extract_tables_specialized(
    pdf_path: Union[str, Path],
    pages: List[int],
    prefer_method: str = "auto"
) -> List[Dict[str, Any]]:
    """
    Extrae tablas usando métodos especializados con pdfplumber y unstructured.
    
    Args:
        pdf_path: Ruta del archivo PDF
        pages: Lista de páginas a procesar
        prefer_method: "auto" o "pdfplumber"
        
    Returns:
        Lista deduplicada de tablas extraídas
    """
    # Validate prefer_method to only allow supported methods
    valid_methods = ("auto", "pdfplumber")
    if prefer_method not in valid_methods:
        raise ValueError(f"prefer_method must be one of {valid_methods}, got: {prefer_method}")
    
    settings = _get_settings()
    
    if not pages:
        logger.info("⚠️ No hay páginas especificadas para extracción tabular")
        return []
    
    logger.info(f"🎯 Iniciando extracción tabular especializada en páginas {pages} con método '{prefer_method}'")
    
    # Use PDF Resource Manager for all extraction methods
    with PDFResourceManager() as pdf_mgr:
        tables = _extract_with_selected_method(pdf_path, pages, prefer_method, pdf_mgr)
    
    logger.info(f"🎯 Extracción completada: {len(tables)} tablas encontradas")
    return tables


def _extract_with_selected_method(
    pdf_path: Union[str, Path],
    pages: List[int],
    method: str,
    pdf_mgr: PDFResourceManager
) -> List[Dict[str, Any]]:
    """
    Extrae tablas usando el método seleccionado.
    
    Args:
        pdf_path: Ruta del archivo PDF
        pages: Lista de páginas a procesar
        method: Método de extracción preferido
        pdf_mgr: Gestor de recursos PDF
        
    Returns:
        Lista de tablas extraídas
    """
    tables = []
    
    try:
        # Currently only supporting pdfplumber as the primary method
        tables = extract_tables_pdfplumber(pdf_path, pages, pdf_mgr)
    except Exception as e:
        logger.warning(f"⚠️ Extracción con {method} falló: {str(e)}")
    
    return tables


def validate_extraction_parameters(
    pdf_path: Union[str, Path],
    pages: List[int],
    prefer_method: str
) -> bool:
    """
    Valida los parámetros de extracción antes de procesar.
    
    Args:
        pdf_path: Ruta del archivo PDF
        pages: Lista de páginas a procesar
        prefer_method: Método de extracción preferido
        
    Returns:
        True si los parámetros son válidos
        
    Raises:
        ValueError: Si algún parámetro es inválido
        FileNotFoundError: Si el archivo PDF no existe
    """
    # Validar archivo PDF
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    if not pdf_file.suffix.lower() == '.pdf':
        raise ValueError(f"File must be a PDF: {pdf_path}")
    
    # Validar páginas
    if not pages:
        raise ValueError("Pages list cannot be empty")
    
    if any(page < 1 for page in pages):
        raise ValueError("Page numbers must be positive integers")
    
    # Validar método
    valid_methods = ("auto", "pdfplumber")
    if prefer_method not in valid_methods:
        raise ValueError(f"prefer_method must be one of {valid_methods}, got: {prefer_method}")
    
    return True






