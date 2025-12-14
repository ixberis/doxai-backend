# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/conversion_dispatcher_refactored.py

Refactored conversion dispatcher - clean, modular, focused.
Main entry point that orchestrates all the specialized handlers.

Author: Ixchel Beristáin Mendoza  
Date: 28/09/2025 - Refactored from 407-line conversion_dispatcher.py
"""

from pathlib import Path
from typing import Dict, Any, Optional, Callable, Union, List
import logging

from .dispatcher_core import FileTypeRouter
from .pdf_conversion_handler import PDFConversionHandler
from .office_conversion_handler import OfficeConversionHandler

logger = logging.getLogger(__name__)


class UniversalConversionDispatcher:
    """
    Clean, modular conversion dispatcher.
    
    Responsibilities:
    1. Route files to appropriate handlers
    2. Validate inputs 
    3. Coordinate conversion process
    
    Delegates actual conversion to specialized handlers.
    """
    
    def __init__(self):
        self.logger = logger
        self.pdf_handler = PDFConversionHandler()
        self.office_handler = OfficeConversionHandler()
    
    async def dispatch_conversion(
        self,
        file_path: Path,
        file_meta: Dict[str, Any],
        operation_id: str,
        job_id: Optional[str] = None,
        cancel_cb: Optional[Callable[[], bool]] = None,
        progress_cb: Optional[Callable[[str, float, Optional[Dict[str, Any]]], None]] = None,
    ) -> Dict[str, Union[str, List]]:
        """
        Dispatch file conversion to appropriate handler based on file type.
        
        Args:
            file_path: Path to the file to convert
            file_meta: File metadata from estimate_conversion_duration
            operation_id: ID for timeout/operation tracking
            job_id: Optional job ID for logging
            cancel_cb: Optional cancellation callback
            progress_cb: Optional progress callback
            
        Returns:
            Dict with 'text', 'tables', 'forms' keys
            
        Raises:
            ValueError: If file type is not supported or conversion fails
        """
        # Validate inputs
        if not file_path or not file_path.exists():
            raise ValueError(f"File does not exist: {file_path}")
        
        file_type = file_meta.get("file_type", "unknown")
        if not FileTypeRouter.is_supported_file_type(file_type):
            raise ValueError(f"Unsupported file type: {file_type}")
        
        converter_type = FileTypeRouter.get_converter_type(file_type)
        
        self.logger.info(f"🔄 Dispatching {file_type.upper()} file to {converter_type} handler ({file_path.name})")
        
        # Route to appropriate handler
        try:
            if converter_type == "pdf":
                return await self.pdf_handler.convert_pdf(
                    file_path, file_meta, operation_id, job_id, cancel_cb, progress_cb
                )
            elif converter_type == "word":
                return self.office_handler.convert_word(
                    file_path, file_meta, operation_id, job_id, cancel_cb, progress_cb
                )
            elif converter_type == "excel":
                return self.office_handler.convert_excel(
                    file_path, file_meta, operation_id, job_id, cancel_cb, progress_cb
                )
            elif converter_type == "powerpoint":
                return self.office_handler.convert_powerpoint(
                    file_path, file_meta, operation_id, job_id, cancel_cb, progress_cb
                )
            elif converter_type == "text":
                return self.office_handler.convert_text(
                    file_path, file_meta, operation_id, job_id, cancel_cb, progress_cb
                )
            else:
                raise ValueError(f"Unknown converter type: {converter_type}")
                
        except Exception as e:
            self.logger.error(f"Conversion failed for {file_type} file {file_path.name}: {e}")
            raise


# Convenience function for backward compatibility
async def dispatch_universal_conversion(
    file_path: Path,
    file_meta: Dict[str, Any],
    operation_id: str,
    job_id: Optional[str] = None,
    cancel_cb: Optional[Callable[[], bool]] = None,
    progress_cb: Optional[Callable[[str, float, Optional[Dict[str, Any]]], None]] = None,
) -> Dict[str, Union[str, List]]:
    """
    Convenience function for universal file conversion dispatch.
    
    This maintains the same API as the original dispatcher for backward compatibility.
    """
    dispatcher = UniversalConversionDispatcher()
    return await dispatcher.dispatch_conversion(
        file_path, file_meta, operation_id, job_id, cancel_cb, progress_cb
    )


# Export the class for direct usage
__all__ = ['UniversalConversionDispatcher', 'dispatch_universal_conversion']






