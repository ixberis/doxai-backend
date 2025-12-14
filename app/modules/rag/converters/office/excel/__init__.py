# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/progress_adapter.py

Progress callback adaptation for different converter types.
Handles progress reporting standardization across converters.

Author: Ixchel Beristáin Mendoza
Date: 28/09/2025 - Refactored from conversion_dispatcher.py
"""

from typing import Dict, Any, Optional, Callable
import logging

from .dispatcher_core import FileTypeRouter

logger = logging.getLogger(__name__)


class ProgressCallbackAdapter:
    """
    Adapts progress callbacks for different converter types.
    Single responsibility: progress callback standardization.
    """
    
    def __init__(self, converter_type: str):
        self.converter_type = converter_type
        self.base_stage = FileTypeRouter.get_stage_name(converter_type)
    
    def create_adapted_callback(
        self, 
        original_cb: Callable[[str, float, Optional[Dict]], None]
    ) -> Callable[[str, float, Optional[Dict]], None]:
        """
        Create an adapted progress callback that maps internal stages to universal stages.
        
        Args:
            original_cb: Original progress callback function
            
        Returns:
            Adapted callback function
        """
        def adapted_callback(internal_stage: str, percent: float, meta: Optional[Dict] = None):
            # Map internal stage to universal stage
            if internal_stage and internal_stage != self.base_stage:
                universal_stage = f"{self.base_stage}:{internal_stage}"
            else:
                universal_stage = self.base_stage
            
            # Ensure percent is in valid range
            percent = max(0.0, min(1.0, float(percent)))
            
            # Call original callback with adapted stage
            original_cb(universal_stage, percent, meta or {})
        
        return adapted_callback
    
    def create_simple_progress_reporter(
        self, 
        progress_cb: Optional[Callable[[str, float, Optional[Dict]], None]],
        job_id: Optional[str] = None
    ):
        """
        Create a simple progress reporter for basic start/complete reporting.
        
        Args:
            progress_cb: Progress callback function
            job_id: Optional job ID for logging
            
        Returns:
            Progress reporter with start() and complete() methods
        """
        if not progress_cb:
            return NullProgressReporter()
            
        return SimpleProgressReporter(
            progress_cb=progress_cb,
            converter_type=self.converter_type,
            base_stage=self.base_stage,
            job_id=job_id
        )


class SimpleProgressReporter:
    """
    Simple progress reporter for basic start/complete reporting.
    """
    
    def __init__(self, progress_cb: Callable, converter_type: str, base_stage: str, job_id: Optional[str] = None):
        self.progress_cb = progress_cb
        self.converter_type = converter_type
        self.base_stage = base_stage
        self.job_id = job_id
    
    def start(self, message: Optional[str] = None):
        """Report conversion start."""
        from .dispatcher_core import DispatcherConfig
        
        default_message = DispatcherConfig.get_progress_message(self.converter_type, "start")
        self.progress_cb("converting", 0.1, {"message": message or default_message})
    
    def complete(self, result: Dict[str, Any], message: Optional[str] = None):
        """Report conversion completion with result statistics."""
        from .dispatcher_core import DispatcherConfig
        
        default_message = DispatcherConfig.get_progress_message(self.converter_type, "complete")
        
        # Build completion metadata
        meta = {
            "message": message or default_message,
            "text_length": len(result.get("text", "")),
            "tables_count": len(result.get("tables", [])),
            "forms_count": len(result.get("forms", []))
        }
        
        # Add converter-specific metadata
        if self.converter_type == "pdf":
            meta.update({
                "extraction_mode": result.get("extraction_mode", "unknown"),
                "no_text_extracted": result.get("no_text_extracted", False)
            })
        
        self.progress_cb("converting", 0.9, meta)
    
    def error(self, error: Exception):
        """Report conversion error."""
        self.progress_cb("converting", 0.0, {"error": str(error)})


class NullProgressReporter:
    """
    Null object pattern for when no progress callback is provided.
    """
    
    def start(self, message: Optional[str] = None):
        pass
    
    def complete(self, result: Dict[str, Any], message: Optional[str] = None):
        pass
    
    def error(self, error: Exception):
        pass







