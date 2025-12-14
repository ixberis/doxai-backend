# -*- coding: utf-8 -*-
"""
backend/app/utils/pdf_resource_manager.py

Context manager para gestión explícita de recursos PDF.
Previene memory leaks y archivos bloqueados durante shutdown.

Author: Sistema de IA
Date: 08/09/2025
"""

from __future__ import annotations

import gc
import logging
from pathlib import Path
from typing import Dict, Set, Any, Optional, List
from contextlib import contextmanager
import weakref
import functools

logger = logging.getLogger(__name__)

class PDFResourceTracker:
    """Rastrea recursos PDF activos para cleanup explícito."""
    
    def __init__(self):
        self.active_files: Set[Path] = set()
        self.pdfplumber_objects: List[weakref.ref] = []
        self.other_resources: Dict[str, Any] = {}
        
    def register_file(self, file_path: Path) -> None:
        """Registra un archivo PDF como activo."""
        self.active_files.add(Path(file_path))
        logger.debug(f"📝 Registered PDF file: {file_path}")
        
    def register_pdfplumber_object(self, obj: Any) -> None:
        """Registra un objeto pdfplumber para cleanup."""
        if obj is not None:
            self.pdfplumber_objects.append(weakref.ref(obj))
            logger.debug("📝 Registered pdfplumber object")
    
    def force_cleanup(self) -> None:
        """Fuerza el cleanup de todos los recursos rastreados."""
        cleanup_count = 0
        
        # Cleanup pdfplumber objects
        for ref in self.pdfplumber_objects:
            obj = ref()
            if obj is not None:
                try:
                    if hasattr(obj, 'close'):
                        obj.close()
                    cleanup_count += 1
                except Exception as e:
                    logger.warning(f"⚠️ Error cleaning pdfplumber object: {e}")
        
        # Clear references
        self.pdfplumber_objects.clear()
        self.other_resources.clear()
        
        # Force garbage collection
        gc.collect()
        
        if cleanup_count > 0:
            logger.info(f"🧹 Cleaned up {cleanup_count} PDF resources")
        
        # Log active files (informational)
        if self.active_files:
            logger.debug(f"📄 Active files tracked: {len(self.active_files)}")
            
    def get_active_files(self) -> Set[Path]:
        """Retorna los archivos PDF actualmente activos."""
        return self.active_files.copy()


class PDFResourceManager:
    """Context manager para gestión automática de recursos PDF."""
    
    def __init__(self):
        self.tracker = PDFResourceTracker()
        
    def __enter__(self) -> PDFResourceTracker:
        logger.debug("🚀 PDF Resource Manager started")
        return self.tracker
        
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            self.tracker.force_cleanup()
            logger.debug("✅ PDF Resource Manager cleanup completed")
        except Exception as e:
            logger.error(f"❌ Error during PDF resource cleanup: {e}")
        
        # Suppress exceptions during cleanup to avoid masking original errors
        return False


def with_pdf_resource_cleanup(func):
    """Decorator para funciones que usan recursos PDF."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with PDFResourceManager() as pdf_mgr:
            # Inyectar el manager como primer argumento si la función lo acepta
            import inspect
            sig = inspect.signature(func)
            if 'pdf_mgr' in sig.parameters:
                kwargs['pdf_mgr'] = pdf_mgr
            return func(*args, **kwargs)
    return wrapper


# Global registry para cleanup en shutdown
_global_trackers: List[PDFResourceTracker] = []

def register_global_tracker(tracker: PDFResourceTracker) -> None:
    """Registra un tracker globalmente para cleanup en shutdown."""
    _global_trackers.append(tracker)

def force_cleanup_all_pdf_resources() -> None:
    """Fuerza cleanup de todos los recursos PDF globales."""
    total_cleaned = 0
    for tracker in _global_trackers:
        try:
            tracker.force_cleanup()
            total_cleaned += 1
        except Exception as e:
            logger.error(f"❌ Error cleaning global PDF tracker: {e}")
    
    _global_trackers.clear()
    if total_cleaned > 0:
        logger.info(f"🧹 Global cleanup: {total_cleaned} PDF trackers cleaned")






