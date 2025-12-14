# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/conversion_runner.py

Simple conversion runner - provides a simplified interface for document conversion.

Author: DoxAI
Date: 10/10/2025
"""

from pathlib import Path
from typing import Dict, Any, Optional, Union
import logging

from .conversion_dispatcher import UniversalConversionDispatcher
# TODO: Implementar módulo RAG completo
# from app.modules.rag.utils.estimate_conversion_duration import estimate_conversion_duration

logger = logging.getLogger(__name__)


async def run_conversion(
    file_path: Union[str, Path],
    options: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Run document conversion with simplified interface.
    
    This is a convenience function that wraps UniversalConversionDispatcher
    with a simpler API for common use cases.
    
    Args:
        file_path: Path to the file to convert (str or Path)
        options: Optional conversion options dict with keys:
            - extract_tables: bool - Whether to extract tables
            - extract_forms: bool - Whether to extract forms
            - ocr_enabled: bool - Whether to enable OCR
            - page_range: tuple - (start, end) page range for PDFs
            - job_id: str - Job ID for tracking
            
    Returns:
        Dict with conversion results containing:
            - text: str - Extracted text content
            - tables: list - Extracted tables (if any)
            - forms: list - Extracted forms (if any)
            - metadata: dict - File metadata
            - success: bool - Whether conversion succeeded
            - error: str - Error message (if failed)
            
    Example:
        >>> result = run_conversion("document.pdf")
        >>> print(result['text'])
        
        >>> result = run_conversion("document.pdf", options={
        ...     'extract_tables': True,
        ...     'page_range': (1, 5)
        ... })
    """
    try:
        # Convert str to Path
        if isinstance(file_path, str):
            file_path = Path(file_path)
        
        # Validate file exists
        if not file_path.exists():
            return {
                'success': False,
                'error': f"File not found: {file_path}",
                'text': '',
                'tables': [],
                'forms': []
            }
        
        # Extract options
        options = options or {}
        job_id = options.get('job_id', 'conversion_job')
        
        # Estimate conversion duration to get file metadata
        file_meta = estimate_conversion_duration(str(file_path), job_id)
        
        # Create dispatcher and run conversion
        dispatcher = UniversalConversionDispatcher()
        
        result = await dispatcher.dispatch_conversion(
            file_path=file_path,
            file_meta=file_meta,
            operation_id=job_id,
            job_id=job_id,
            cancel_cb=None,
            progress_cb=None
        )
        
        # Add success flag and metadata
        result['success'] = True
        result['metadata'] = {
            'file_type': file_meta.get('file_type', 'unknown'),
            'pages': file_meta.get('num_pages', 0),
            'estimated_duration': file_meta.get('estimated_duration_secs', 0)
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Conversion failed for {file_path}: {e}")
        return {
            'success': False,
            'error': str(e),
            'text': '',
            'tables': [],
            'forms': []
        }


__all__ = ['run_conversion']







