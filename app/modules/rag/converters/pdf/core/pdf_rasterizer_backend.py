# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_rasterizer_backend.py

Sistema de selección de backend de rasterización para PDFs.
Prioriza Ghostscript > Poppler > PyMuPDF según disponibilidad.

Author: Ixchel Beristáin Mendoza
Date: 13/10/2025
"""

import logging
import os
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class RasterizerBackend(Enum):
    """Backends disponibles para rasterización de PDFs."""
    GHOSTSCRIPT = "ghostscript"
    POPPLER = "poppler"
    PYMUPDF = "pymupdf"


class PDFRasterizerSelector:
    """
    Selecciona el backend de rasterización óptimo según disponibilidad.
    Orden de preferencia: Ghostscript > Poppler > PyMuPDF
    """
    
    def __init__(self):
        """Initialize rasterizer selector."""
        self._preferred_backend: Optional[RasterizerBackend] = None
        self._backend_cache: dict = {}
        self._detect_backends()
    
    def _detect_backends(self) -> None:
        """Detecta backends disponibles en el sistema."""
        import shutil
        
        # Detect Ghostscript
        gs_commands = ["gswin64c", "gswin32c", "gs"]
        for cmd in gs_commands:
            if shutil.which(cmd):
                self._backend_cache[RasterizerBackend.GHOSTSCRIPT] = cmd
                logger.debug(f"✅ Ghostscript disponible: {cmd}")
                break
        
        # Detect Poppler
        if shutil.which("pdftoppm"):
            self._backend_cache[RasterizerBackend.POPPLER] = "pdftoppm"
            logger.debug("✅ Poppler disponible")
        
        # Detect PyMuPDF
        try:
            import fitz
            self._backend_cache[RasterizerBackend.PYMUPDF] = True
            logger.debug("✅ PyMuPDF disponible")
        except ImportError:
            logger.debug("⚠️ PyMuPDF no disponible")
    
    def get_preferred_backend(self) -> RasterizerBackend:
        """
        Obtiene el backend de rasterización preferido según disponibilidad y configuración.
        
        Returns:
            Backend preferido (Ghostscript > Poppler > PyMuPDF)
        """
        if self._preferred_backend:
            return self._preferred_backend
        
        # Check environment variable override
        env_backend = os.getenv("RASTER_BACKEND", "").lower()
        if env_backend == "ghostscript" and RasterizerBackend.GHOSTSCRIPT in self._backend_cache:
            self._preferred_backend = RasterizerBackend.GHOSTSCRIPT
            logger.info("⚙️ Backend de rasterización forzado por env: ghostscript")
            return self._preferred_backend
        elif env_backend == "poppler" and RasterizerBackend.POPPLER in self._backend_cache:
            self._preferred_backend = RasterizerBackend.POPPLER
            logger.info("⚙️ Backend de rasterización forzado por env: poppler")
            return self._preferred_backend
        elif env_backend == "pymupdf" and RasterizerBackend.PYMUPDF in self._backend_cache:
            self._preferred_backend = RasterizerBackend.PYMUPDF
            logger.info("⚙️ Backend de rasterización forzado por env: pymupdf")
            return self._preferred_backend
        
        # Auto-select based on priority
        if RasterizerBackend.GHOSTSCRIPT in self._backend_cache:
            self._preferred_backend = RasterizerBackend.GHOSTSCRIPT
            logger.info("⚙️ Backend de rasterización seleccionado: ghostscript (preferido)")
        elif RasterizerBackend.POPPLER in self._backend_cache:
            self._preferred_backend = RasterizerBackend.POPPLER
            logger.info("⚙️ Backend de rasterización seleccionado: poppler (fallback)")
        elif RasterizerBackend.PYMUPDF in self._backend_cache:
            self._preferred_backend = RasterizerBackend.PYMUPDF
            logger.info("⚙️ Backend de rasterización seleccionado: pymupdf (fallback)")
        else:
            logger.error("❌ No hay backends de rasterización disponibles")
            self._preferred_backend = RasterizerBackend.PYMUPDF  # Fallback
        
        return self._preferred_backend
    
    def is_available(self, backend: RasterizerBackend) -> bool:
        """
        Verifica si un backend específico está disponible.
        
        Args:
            backend: Backend a verificar
            
        Returns:
            True si el backend está disponible
        """
        return backend in self._backend_cache
    
    def get_backend_command(self, backend: RasterizerBackend) -> Optional[str]:
        """
        Obtiene el comando/path del backend especificado.
        
        Args:
            backend: Backend del cual obtener el comando
            
        Returns:
            Comando o None si no está disponible
        """
        return self._backend_cache.get(backend)
    
    def get_available_backends(self) -> list[RasterizerBackend]:
        """
        Obtiene lista de todos los backends disponibles.
        
        Returns:
            Lista de backends disponibles
        """
        return list(self._backend_cache.keys())
    
    def get_backend_info(self) -> dict:
        """
        Obtiene información completa sobre backends disponibles.
        
        Returns:
            Dict con información de backends
        """
        preferred = self.get_preferred_backend()
        return {
            "preferred": preferred.value,
            "available": [b.value for b in self.get_available_backends()],
            "ghostscript": self.is_available(RasterizerBackend.GHOSTSCRIPT),
            "poppler": self.is_available(RasterizerBackend.POPPLER),
            "pymupdf": self.is_available(RasterizerBackend.PYMUPDF),
        }


# Global singleton instance
_rasterizer_selector: Optional[PDFRasterizerSelector] = None


def get_rasterizer_selector() -> PDFRasterizerSelector:
    """
    Obtiene la instancia singleton del selector de rasterizador.
    
    Returns:
        Instancia global de PDFRasterizerSelector
    """
    global _rasterizer_selector
    if _rasterizer_selector is None:
        _rasterizer_selector = PDFRasterizerSelector()
    return _rasterizer_selector


def get_preferred_rasterizer() -> RasterizerBackend:
    """
    Función de conveniencia para obtener el backend preferido.
    
    Returns:
        Backend de rasterización preferido
    """
    return get_rasterizer_selector().get_preferred_backend()







