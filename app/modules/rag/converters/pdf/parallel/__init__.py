# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_page_ocr_processor_refactored.py

Refactored PDF page OCR processor - clean coordination of specialized components.
Main entry point that maintains backward compatibility while using modular architecture.

Author: Ixchel Beristáin Mendoza
Date: 28/09/2025 - Refactored from 374-line pdf_page_ocr_processor.py
"""

import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Union

# ARCHIVED: OCR local memory/timeout managers moved to backend/archived/ocr_local/
# from .pdf_ocr_memory_manager import PDFOCRMemoryManager
# from .pdf_ocr_timeout_manager import PDFOCRTimeoutManager
# Still active:
from .pdf_ocr_engine import PDFOCREngine
from .pdf_ocr_retry_handler import PDFOCRRetryHandler, RetryStrategy

logger = logging.getLogger(__name__)

# Check dependencies
try:
    from app.shared.config import settings
    # TODO: Implementar módulo RAG completo
    # from app.modules.rag.converters.pdf_image_preprocessing import get_preprocessor
    HAS_DEPENDENCIES = False  # Temporalmente False hasta implementar RAG
except ImportError as e:
    logger.error(f"❌ Missing dependencies for page OCR processor: {e}")
    HAS_DEPENDENCIES = False


class PageOCRProcessorRefactored:
    """
    Clean, modular PDF page OCR processor.
    
    Responsibilities:
    1. Maintain backward compatibility API
    2. Coordinate specialized components
    3. Provide unified interface for PDF page OCR
    
    Delegates actual work to specialized handlers.
    """
    
    def __init__(self):
        """Initialize with specialized components (OCR local archived)."""
        if not HAS_DEPENDENCIES:
            raise ImportError("Required dependencies not available for PageOCRProcessorRefactored")
        
        # FASE 5: OCR local components archived
        # Memory and timeout managers moved to backend/archived/ocr_local/
        # self.memory_manager = PDFOCRMemoryManager(...)
        # self.timeout_manager = PDFOCRTimeoutManager(...)
        
        # Still active components:
        self.ocr_engine = PDFOCREngine()
        self.retry_handler = PDFOCRRetryHandler(
            max_retries=2,
            retry_strategy=RetryStrategy.LINEAR_BACKOFF
        )
        
        # Get preprocessor
        self.preprocessor = get_preprocessor()
        
        # Configuration from settings
        self.ocr_lang = getattr(settings.ocr, 'lang', 'spa')
        if hasattr(self.ocr_lang, 'value'):
            self.ocr_lang = self.ocr_lang.value
            
        self.log_per_page = getattr(settings.logging, 'ocr_per_page', True)
        self.log_timing = getattr(settings.logging, 'ocr_timing_details', True)
        
        # FASE 5: Log warning about archived OCR
        logger.warning("⚠️ PageOCRProcessor initialized but OCR local components archived - limited functionality")
    
    def process_single_page(
        self, 
        pdf_path: Union[str, Path], 
        page_num: int,
        strategy: str = "hi_res",
        timeout_override: Optional[int] = None,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Process a single PDF page with OCR optimization.
        
        Maintains exact same API as original implementation.
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number (0-indexed for internal, 1-indexed for display)
            strategy: OCR strategy ("fast" or "hi_res")
            timeout_override: Override timeout in seconds
            **kwargs: Additional parameters for backward compatibility
            
        Returns:
            Dictionary with OCR results or None if failed
        """
        page_display_num = page_num + 1  # Convert to 1-indexed for display
        start_time = time.time()
        
        if self.log_per_page:
            logger.info(f"🔄 [PAGE {page_display_num}] Starting OCR processing with {strategy} strategy")
        
        # Check memory before starting
        if not self.memory_manager.check_memory_before_operation(page_display_num, "OCR"):
            logger.error(f"❌ [PAGE {page_display_num}] Skipping due to memory constraints")
            return None
        
        try:
            # Calculate timeout allocations
            effective_timeout = timeout_override or self.timeout_manager.default_timeout_sec
            timeout_allocation = self.timeout_manager.calculate_phase_timeouts(
                effective_timeout, 
                has_preprocessing=(strategy == "hi_res" and getattr(settings.ocr, 'deskew', False))
            )
            
            # Step 1: Preprocessing (if enabled and needed)
            processed_image = None
            if strategy == "hi_res" and getattr(settings.ocr, 'deskew', False):
                preprocessing_start = time.time()
                
                try:
                    processed_image = self.preprocessor.preprocess_with_fallback(
                        pdf_path, page_num, timeout_allocation["preprocessing"]
                    )
                    
                    preprocessing_time = time.time() - preprocessing_start
                    
                    if self.log_timing:
                        logger.info(f"⏱️ [PAGE {page_display_num}] Preprocessing: {preprocessing_time:.2f}s")
                    
                    # Check if preprocessing took too long
                    if preprocessing_time > timeout_allocation["preprocessing"]:
                        if getattr(settings.logging, 'ocr_strategy_switch', True):
                            logger.warning(f"🔄 [PAGE {page_display_num}] Preprocessing timeout, using direct OCR")
                        processed_image = None
                        
                except Exception as e:
                    logger.warning(f"⚠️ [PAGE {page_display_num}] Preprocessing failed: {e}, using direct OCR")
                    processed_image = None
            
            # Step 2: OCR Processing
            ocr_start = time.time()
            
            if processed_image is not None:
                # Use preprocessed image
                result = self.ocr_engine.ocr_from_image_array(
                    processed_image, page_display_num, strategy
                )
            else:
                # Direct PDF processing
                result = self.ocr_engine.ocr_from_pdf_page(
                    pdf_path, page_num, strategy, timeout_allocation["ocr"]
                )
            
            ocr_time = time.time() - ocr_start
            total_time = time.time() - start_time
            
            # Track memory after processing
            memory_stats = self.memory_manager.track_memory_after_operation(page_display_num, "OCR")
            
            if self.log_timing:
                logger.info(f"⏱️ [PAGE {page_display_num}] OCR: {ocr_time:.2f}s, "
                           f"Total: {total_time:.2f}s, RAM: {memory_stats['current_mb']:.1f}MB")
            
            # Check timeout and handle fallback
            if total_time > effective_timeout:
                logger.warning(f"⏰ [PAGE {page_display_num}] Processing exceeded timeout "
                             f"({total_time:.2f}s > {effective_timeout}s)")
                
                if result:
                    # Return partial result if we have something
                    return result
                else:
                    # Attempt fallback processing
                    return self._attempt_fallback_processing(pdf_path, page_num, timeout_allocation["fallback"])
            
            # Validate and log result
            if result and self.ocr_engine.validate_ocr_result(result, page_display_num):
                if self.log_per_page:
                    text_length = len(result.get("text", ""))
                    tables_count = len(result.get("tables", []))
                    logger.info(f"✅ [PAGE {page_display_num}] OCR completed: "
                               f"{text_length} chars, {tables_count} tables")
                
                return result
            else:
                # Attempt fallback for invalid results
                return self._attempt_fallback_processing(pdf_path, page_num, timeout_allocation["fallback"])
            
        except Exception as e:
            logger.error(f"❌ [PAGE {page_display_num}] OCR processing failed: {e}")
            return self._attempt_fallback_processing(pdf_path, page_num, effective_timeout // 2)
    
    def _attempt_fallback_processing(
        self, 
        pdf_path: Union[str, Path], 
        page_num: int, 
        timeout_sec: int
    ) -> Optional[Dict[str, Any]]:
        """
        Attempt fallback OCR processing with reduced settings.
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number (0-indexed)
            timeout_sec: Reduced timeout
            
        Returns:
            Fallback OCR results or None
        """
        page_display_num = page_num + 1
        
        if getattr(settings.logging, 'ocr_strategy_switch', True):
            logger.info(f"🔄 [PAGE {page_display_num}] Attempting fallback with fast strategy")
        
        try:
            # Try fast strategy as fallback
            return self.ocr_engine.ocr_from_pdf_page(
                pdf_path, page_num, "fast", timeout_sec
            )
            
        except Exception as e:
            logger.error(f"❌ [PAGE {page_display_num}] Fallback processing also failed: {e}")
            return None
    
    def process_page_with_retry(
        self,
        pdf_path: Union[str, Path],
        page_num: int,
        max_retries: int = 2,
        strategy: str = "hi_res"
    ) -> Optional[Dict[str, Any]]:
        """
        Process page with retry logic for transient failures.
        
        Maintains exact same API as original implementation.
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number (0-indexed)
            max_retries: Maximum retry attempts
            strategy: OCR strategy
            
        Returns:
            OCR results or None after all retries exhausted
        """
        # Configure retry handler for this operation
        retry_handler = PDFOCRRetryHandler(
            max_retries=max_retries,
            retry_strategy=RetryStrategy.LINEAR_BACKOFF
        )
        
        # Execute with retry logic
        def ocr_operation(**kwargs):
            return self.process_single_page(pdf_path, page_num, strategy, **kwargs)
        
        result = retry_handler.execute_with_retry(
            operation_func=ocr_operation,
            page_num=page_num,
            operation_name="OCR"
        )
        
        return result
    
    # New methods that expose additional functionality
    def get_processing_status(self) -> Dict[str, Any]:
        """
        Get current processing system status.
        
        Returns:
            Status information dictionary
        """
        memory_stats = self.memory_manager.get_current_memory_usage()
        retry_stats = self.retry_handler.get_retry_statistics()
        
        return {
            "memory": {
                "current_mb": memory_stats['current_mb'],
                "usage_percentage": memory_stats['usage_percentage'],
                "peak_mb": memory_stats['peak_mb'],
                "conservative_mode": self.memory_manager.should_use_memory_conservative_mode()
            },
            "retry_statistics": retry_stats,
            "system_ready": True,
            "components": {
                "memory_manager": True,
                "ocr_engine": True,
                "timeout_manager": True,
                "retry_handler": True,
                "preprocessor": hasattr(self, 'preprocessor')
            }
        }
    
    def cleanup_resources(self):
        """
        Clean up resources and reset statistics.
        """
        # Force garbage collection
        self.memory_manager.force_garbage_collection()
        
        # Reset retry statistics
        self.retry_handler.reset_statistics()
        
        logger.info("🧹 OCR processor resources cleaned up")


# Global processor instance for backward compatibility
_processor_instance = None

def get_page_processor() -> PageOCRProcessorRefactored:
    """
    Get singleton page processor instance.
    
    Maintains exact same API as original implementation.
    """
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = PageOCRProcessorRefactored()
    return _processor_instance


# Convenience functions for backward compatibility
def process_single_page(pdf_path: Union[str, Path], page_num: int, **kwargs) -> Optional[Dict[str, Any]]:
    """
    Convenience function for processing a single page.
    
    Maintains exact same API as original implementation.
    """
    return get_page_processor().process_single_page(pdf_path, page_num, **kwargs)


def process_page_with_retry(pdf_path: Union[str, Path], page_num: int, **kwargs) -> Optional[Dict[str, Any]]:
    """
    Convenience function for processing with retry.
    
    Maintains exact same API as original implementation.
    """
    return get_page_processor().process_page_with_retry(pdf_path, page_num, **kwargs)


# Export main functions - same as original
__all__ = [
    'PageOCRProcessorRefactored',
    'get_page_processor',
    'process_single_page', 
    'process_page_with_retry'
]

# Alias for backward compatibility
PageOCRProcessor = PageOCRProcessorRefactored







