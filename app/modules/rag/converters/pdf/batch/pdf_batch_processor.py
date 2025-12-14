# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_batch_processor.py

Batch processing operations for PDF pages with cache integration.
Single responsibility: processing batches of PDF pages efficiently.

Author: Ixchel Beristáin Mendoza
Date: 28/09/2025 - Refactored from pdf_cached_page_processor.py  
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
import logging

from app.shared.config import settings
from .pdf_cache_operations import PDFCacheOperations
from .pdf_processing_metrics import PDFProcessingMetricsCollector

logger = logging.getLogger(__name__)


class PDFBatchProcessor:
    """
    Processes batches of PDF pages with integrated caching.
    Single responsibility: batch-level page processing coordination.
    """
    
    def __init__(self):
        self.cache_ops = PDFCacheOperations()
        self.metrics_collector = PDFProcessingMetricsCollector()
        
        # Import here to avoid circular dependencies
        from .pdf_page_ocr_processor_refactored import PageOCRProcessor
        self.page_processor = PageOCRProcessor()
    
    def process_pages_batch(
        self,
        pdf_path: Path,
        pages: List[int],
        job_id: str,
        processing_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process a specific batch of PDF pages with cache optimization.
        
        Args:
            pdf_path: Path to PDF file
            pages: List of page numbers to process
            job_id: Job identifier for tracking
            processing_config: Optional processing configuration
            
        Returns:
            Batch processing results with metrics
        """
        try:
            config = processing_config or {}
            
            # Initialize batch results
            batch_results = {
                'job_id': job_id,
                'processed_pages': [],
                'cache_hits': 0,
                'cache_misses': 0,
                'errors': [],
                'success': True
            }
            
            logger.info(f"🔄 Starting batch processing: {len(pages)} pages for {pdf_path.name}")
            
            # Process each page in the batch
            for page_num in pages:
                page_result = self._process_single_page_with_cache(
                    pdf_path, page_num, config
                )
                
                # Record metrics based on result
                if page_result.get('cache_hit', False):
                    batch_results['cache_hits'] += 1
                    self.metrics_collector.record_page_operation(page_num, "cache_hit")
                else:
                    batch_results['cache_misses'] += 1
                    self.metrics_collector.record_page_operation(page_num, "cache_miss")
                
                if page_result.get('success', False):
                    batch_results['processed_pages'].append(page_num)
                    self.metrics_collector.record_page_operation(
                        page_num, "processing", success=True
                    )
                else:
                    error_info = {
                        'page': page_num,
                        'error': page_result.get('error', 'Unknown processing error')
                    }
                    batch_results['errors'].append(error_info)
                    self.metrics_collector.record_page_operation(
                        page_num, "processing", success=False, 
                        error=error_info['error']
                    )
            
            # Determine overall batch success
            batch_results['success'] = len(batch_results['errors']) == 0
            
            logger.info(f"📊 Batch completed: {len(batch_results['processed_pages'])} pages processed, "
                       f"{batch_results['cache_hits']} cache hits, {len(batch_results['errors'])} errors")
            
            return batch_results
            
        except Exception as e:
            logger.error(f"❌ Batch processing failed for {pdf_path.name}: {e}")
            return {
                'job_id': job_id,
                'success': False,
                'error': str(e),
                'processed_pages': [],
                'cache_hits': 0,
                'cache_misses': 0,
                'errors': [{'page': 'batch', 'error': str(e)}]
            }
    
    def _process_single_page_with_cache(
        self, 
        pdf_path: Path, 
        page_num: int, 
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process a single page with cache check and storage.
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number to process  
            config: Processing configuration
            
        Returns:
            Page processing result with cache information
        """
        try:
            # Check cache first
            cached_result = self.cache_ops.get_cached_page_result(
                pdf_path, 
                page_num, 
                config.get('dpi', settings.OCR_BASE_DPI)
            )
            
            if cached_result:
                logger.debug(f"📦 Using cached result for page {page_num}")
                cached_result['cache_hit'] = True
                return cached_result
            
            # Process page if not cached
            logger.debug(f"💨 Processing page {page_num} (cache miss)")
            
            page_result = self.page_processor.process_single_page(
                pdf_path=pdf_path,
                page_number=page_num,
                **config
            )
            
            # Add cache information
            page_result['cache_hit'] = False
            
            # Cache successful results
            if page_result.get('success', False):
                cache_success = self.cache_ops.cache_page_result(
                    pdf_path, 
                    page_num, 
                    page_result, 
                    config.get('dpi')
                )
                page_result['cached'] = cache_success
            
            return page_result
            
        except Exception as e:
            logger.error(f"❌ Error processing page {page_num}: {e}")
            return {
                'success': False,
                'error': str(e),
                'page_number': page_num,
                'cache_hit': False,
                'cached': False
            }
    
    def get_batch_metrics(self) -> Dict[str, Any]:
        """Get current batch processing metrics."""
        return self.metrics_collector.get_current_metrics()
    
    def reset_metrics(self):
        """Reset metrics for new batch processing session."""
        self.metrics_collector = PDFProcessingMetricsCollector()






