# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_cache_operations.py

PDF-specific cache operations for page-level caching.
Single responsibility: cache management for PDF page processing.

Author: Ixchel Beristáin Mendoza
Date: 28/09/2025 - Refactored from pdf_cached_page_processor.py
"""

from pathlib import Path
from typing import Dict, Any, Optional
import logging

from app.shared.config import settings
from app.shared.enums.ocr_optimization_enum import OCREngine, OCRLanguage

logger = logging.getLogger(__name__)


def clear_cache_for_file(controller, pdf_path: Path) -> bool:
    """
    Compatibility helper: tries available methods in the current controller.
    Supports both legacy and modern cache clearing APIs.
    """
    # 1) Legacy API
    if hasattr(controller, "clear_file_cache"):
        return bool(controller.clear_file_cache(pdf_path))
    
    # 2) Modern API: by document path
    if hasattr(controller, "clear_document_cache"):
        return bool(controller.clear_document_cache(pdf_path))
    
    # 3) Modern API: by job_id (if applicable)
    if hasattr(controller, "clear_job_cache"):
        try:
            return bool(controller.clear_job_cache(None))
        except Exception:
            return False
    
    return False


class PDFCacheOperations:
    """
    Handles PDF page-level cache operations.
    Single responsibility: cache get/set/clear operations for PDF pages.
    """
    
    def __init__(self):
        # Import cache manager here to avoid circular imports
        from ..cache.page_cache_controller import PageCacheController
        self.cache_manager = PageCacheController()
    
    def get_cached_page_result(
        self, 
        pdf_path: Path, 
        page_num: int, 
        dpi: Optional[int] = None,
        language: OCRLanguage = OCRLanguage.AUTO,
        engine: OCREngine = OCREngine.TESSERACT
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached result for a PDF page.
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number (1-indexed)
            dpi: DPI setting (defaults to settings.OCR_BASE_DPI)
            language: OCR language setting
            engine: OCR engine setting
            
        Returns:
            Cached page result or None if not found/disabled
        """
        if not settings.CACHE_ENABLE_PAGE_CACHE:
            logger.debug(f"Page cache disabled for {pdf_path.name} page {page_num}")
            return None
        
        try:
            result = self.cache_manager.get_cached_page(
                file_path=pdf_path,
                page_number=page_num,
                dpi=dpi or settings.OCR_BASE_DPI,
                language=language,
                engine=engine
            )
            
            if result:
                logger.debug(f"📦 Cache hit: {pdf_path.name} page {page_num}")
            else:
                logger.debug(f"💨 Cache miss: {pdf_path.name} page {page_num}")
                
            return result
            
        except Exception as e:
            logger.warning(f"Cache retrieval error for {pdf_path.name} page {page_num}: {e}")
            return None
    
    def cache_page_result(
        self, 
        pdf_path: Path, 
        page_num: int, 
        result: Dict[str, Any], 
        dpi: Optional[int] = None,
        language: OCRLanguage = OCRLanguage.AUTO,
        engine: OCREngine = OCREngine.TESSERACT
    ) -> bool:
        """
        Store page processing result in cache.
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number (1-indexed)
            result: Processing result to cache
            dpi: DPI setting used for processing
            language: OCR language setting
            engine: OCR engine setting
            
        Returns:
            True if successfully cached, False otherwise
        """
        if not settings.CACHE_ENABLE_PAGE_CACHE:
            logger.debug(f"Page cache disabled, skipping cache for {pdf_path.name} page {page_num}")
            return False
        
        if not result.get('success', False):
            logger.debug(f"Not caching failed result for {pdf_path.name} page {page_num}")
            return False
        
        try:
            self.cache_manager.cache_page_result(
                file_path=pdf_path,
                page_number=page_num,
                ocr_result=result,
                dpi=dpi or settings.OCR_BASE_DPI,
                language=language,
                engine=engine
            )
            
            logger.debug(f"💾 Cached result for {pdf_path.name} page {page_num}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to cache result for {pdf_path.name} page {page_num}: {e}")
            return False
    
    def clear_document_cache(self, pdf_path: Path) -> bool:
        """
        Clear all cached data for a PDF document.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            True if successfully cleared
        """
        try:
            success = clear_cache_for_file(self.cache_manager, pdf_path)
            if success:
                logger.info(f"🗑️ Cleared cache for {pdf_path.name}")
            else:
                logger.warning(f"Failed to clear cache for {pdf_path.name}")
            return success
            
        except Exception as e:
            logger.error(f"Error clearing cache for {pdf_path.name}: {e}")
            return False
    
    def get_cache_statistics(self, pdf_path: Path) -> Dict[str, Any]:
        """
        Get cache statistics for a PDF document.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Dictionary with cache statistics
        """
        try:
            return self.cache_manager.get_cache_stats(pdf_path)
        except Exception as e:
            logger.error(f"Error getting cache stats for {pdf_path.name}: {e}")
            return {
                'error': str(e),
                'cached_pages': 0,
                'total_size': 0
            }






