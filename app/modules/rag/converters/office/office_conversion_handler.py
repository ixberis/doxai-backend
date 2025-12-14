# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/office_conversion_handler.py

Office document conversion handling (Word, Excel, PowerPoint, Plain text).
Handles all non-PDF file conversions with consistent error handling.

Author: Ixchel Beristáin Mendoza
Date: 28/09/2025 - Refactored from conversion_dispatcher.py
"""

from pathlib import Path
from typing import Dict, Any, Optional, Callable, Union, List
import logging

from .progress_adapter import ProgressCallbackAdapter

logger = logging.getLogger(__name__)


class OfficeConversionHandler:
    """
    Handles conversion of Office documents and plain text files.
    Single responsibility: Non-PDF file conversion orchestration.
    """
    
    def __init__(self):
        self.logger = logger
    
    def convert_word(
        self, 
        file_path: Path, 
        file_meta: Dict[str, Any],
        operation_id: str,
        job_id: Optional[str],
        cancel_cb: Optional[Callable],
        progress_cb: Optional[Callable]
    ) -> Dict[str, Union[str, List]]:
        """
        Convert Word documents (DOCX, DOC, ODT).
        
        Args:
            file_path: Path to Word file
            file_meta: File metadata
            operation_id: Operation ID for tracking
            job_id: Optional job ID for logging  
            cancel_cb: Optional cancellation callback
            progress_cb: Optional progress callback
            
        Returns:
            Dict with 'text', 'tables', 'forms' keys
        """
        adapter = ProgressCallbackAdapter("word")
        progress_reporter = adapter.create_simple_progress_reporter(progress_cb, job_id)
        
        progress_reporter.start()
        
        try:
            from .word_converter import convert_word_to_text
            
            result = convert_word_to_text(str(file_path))
            
            # Validate result
            if result is None:
                raise ValueError("Word conversion returned None")
            
            if not isinstance(result, dict):
                raise ValueError(f"Word conversion returned unexpected type: {type(result)}")
            
            self.logger.info(f"Word conversion completed: {len(result.get('text', ''))} chars, {len(result.get('tables', []))} tables")
            progress_reporter.complete(result)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Word conversion failed: {e}")
            progress_reporter.error(e)
            raise
    
    def convert_excel(
        self, 
        file_path: Path, 
        file_meta: Dict[str, Any],
        operation_id: str,
        job_id: Optional[str],
        cancel_cb: Optional[Callable],
        progress_cb: Optional[Callable]
    ) -> Dict[str, Union[str, List]]:
        """
        Convert Excel/spreadsheet files (XLSX, XLS, ODS, CSV).
        
        Args:
            file_path: Path to Excel file
            file_meta: File metadata
            operation_id: Operation ID for tracking
            job_id: Optional job ID for logging
            cancel_cb: Optional cancellation callback  
            progress_cb: Optional progress callback
            
        Returns:
            Dict with 'text', 'tables', 'forms' keys
        """
        adapter = ProgressCallbackAdapter("excel")
        progress_reporter = adapter.create_simple_progress_reporter(progress_cb, job_id)
        
        progress_reporter.start()
        
        try:
            from .excel_converter import convert_excel_to_text
            
            result = convert_excel_to_text(str(file_path))
            
            # Validate result  
            if result is None:
                raise ValueError("Excel conversion returned None")
            
            if not isinstance(result, dict):
                raise ValueError(f"Excel conversion returned unexpected type: {type(result)}")
            
            self.logger.info(f"Excel conversion completed: {len(result.get('text', ''))} chars, {len(result.get('tables', []))} tables")
            progress_reporter.complete(result)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Excel conversion failed: {e}")
            progress_reporter.error(e)
            raise
    
    def convert_powerpoint(
        self, 
        file_path: Path, 
        file_meta: Dict[str, Any],
        operation_id: str,
        job_id: Optional[str],
        cancel_cb: Optional[Callable],
        progress_cb: Optional[Callable]
    ) -> Dict[str, Union[str, List]]:
        """
        Convert PowerPoint files (PPTX, PPT, ODP).
        
        Args:
            file_path: Path to PowerPoint file
            file_meta: File metadata
            operation_id: Operation ID for tracking
            job_id: Optional job ID for logging
            cancel_cb: Optional cancellation callback
            progress_cb: Optional progress callback
            
        Returns:
            Dict with 'text', 'tables', 'forms' keys
        """
        adapter = ProgressCallbackAdapter("powerpoint")
        progress_reporter = adapter.create_simple_progress_reporter(progress_cb, job_id)
        
        progress_reporter.start()
        
        try:
            from .pptx_converter import convert_pptx_to_text
            
            result = convert_pptx_to_text(str(file_path))
            
            if not result:
                raise ValueError("PowerPoint conversion returned None")
            
            self.logger.info(f"PowerPoint conversion completed: {len(result.get('text', ''))} chars, {len(result.get('tables', []))} tables")
            progress_reporter.complete(result)
            
            return result
            
        except Exception as e:
            self.logger.error(f"PowerPoint conversion failed: {e}")
            progress_reporter.error(e)
            raise
    
    def convert_text(
        self, 
        file_path: Path, 
        file_meta: Dict[str, Any],
        operation_id: str,
        job_id: Optional[str],
        cancel_cb: Optional[Callable],
        progress_cb: Optional[Callable]
    ) -> Dict[str, Union[str, List]]:
        """
        Convert plain text files (TXT).
        
        Args:
            file_path: Path to text file
            file_meta: File metadata
            operation_id: Operation ID for tracking
            job_id: Optional job ID for logging
            cancel_cb: Optional cancellation callback
            progress_cb: Optional progress callback
            
        Returns:
            Dict with 'text', 'tables', 'forms' keys
        """
        adapter = ProgressCallbackAdapter("text")
        progress_reporter = adapter.create_simple_progress_reporter(progress_cb, job_id)
        
        progress_reporter.start()
        
        try:
            from .plain_text_loader import load_plain_text
            
            text_content = load_plain_text(str(file_path))
            
            if not text_content:
                raise ValueError("Text loading returned None or empty")
            
            result = {
                "text": text_content,
                "tables": [],  # Plain text files don't have structured tables
                "forms": []    # Plain text files don't have forms
            }
            
            self.logger.info(f"Text loading completed: {len(text_content)} chars")
            progress_reporter.complete(result)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Text loading failed: {e}")
            progress_reporter.error(e)
            raise






