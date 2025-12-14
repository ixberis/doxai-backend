# -*- coding: utf-8 -*-
"""
backend/app/shared/core/system_tools_cache.py

Verificación de herramientas del sistema (Tesseract, Ghostscript, Poppler).
Detecta disponibilidad de binarios externos para OCR y rasterización PDF.

Autor: Ixchel Beristain
Fecha: 05/09/2025
Actualizado:
- 2025-10-24: Extraído de resource_cache.py para mejor modularidad
"""

from __future__ import annotations
from typing import Optional
import shutil
import logging

logger = logging.getLogger(__name__)


def check_tesseract_availability() -> bool:
    """Verifica si Tesseract está disponible en el sistema."""
    try:
        tesseract_path = shutil.which("tesseract")
        if tesseract_path:
            logger.info(f"✅ Tesseract encontrado en: {tesseract_path}")
            return True
        else:
            logger.warning("⚠️ Tesseract no encontrado; flujos de OCR serán limitados. PDFs escaneados usarán fallback a fast.")
            return False
    except Exception as e:
        logger.warning(f"⚠️ Error verificando Tesseract: {e}")
        return False


def check_ghostscript_availability() -> tuple[bool, Optional[str]]:
    """
    Verifica si Ghostscript está disponible en el sistema.
    
    Returns:
        Tuple (disponible, ruta) donde disponible es True si se encontró
        y ruta es la ubicación del binario o None si no se encontró.
    """
    try:
        # En Windows, buscar gswin64c o gswin32c
        # En Linux/Mac, buscar gs
        gs_commands = ["gswin64c", "gswin32c", "gs"]
        
        for cmd in gs_commands:
            gs_path = shutil.which(cmd)
            if gs_path:
                logger.info(f"✅ Ghostscript encontrado en: {gs_path}")
                return True, gs_path
        
        logger.warning("⚠️ Ghostscript no encontrado en PATH; usando PyMuPDF como backend de rasterización")
        return False, None
        
    except Exception as e:
        logger.warning(f"⚠️ Error verificando Ghostscript: {e}")
        return False, None


def check_poppler_availability() -> tuple[bool, Optional[str]]:
    """
    Verifica si Poppler (pdftoppm) está disponible en el sistema.
    
    Returns:
        Tuple (disponible, ruta) donde disponible es True si se encontró
        y ruta es la ubicación del binario o None si no se encontró.
    """
    try:
        poppler_path = shutil.which("pdftoppm")
        if poppler_path:
            logger.info(f"✅ Poppler (pdftoppm) encontrado en: {poppler_path}")
            return True, poppler_path
        else:
            logger.debug("ℹ️ Poppler no encontrado; usando PyMuPDF como backend de rasterización")
            return False, None
    except Exception as e:
        logger.warning(f"⚠️ Error verificando Poppler: {e}")
        return False, None


# Fin del archivo backend/app/shared/core/system_tools_cache.py
