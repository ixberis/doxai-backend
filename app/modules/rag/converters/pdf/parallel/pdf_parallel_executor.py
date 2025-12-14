# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_parallel_executor.py

Parallel execution engine for PDF page processing.
Single responsibility: executing parallel page processing with ProcessPoolExecutor.

Author: Refactored from pdf_batch_coordinator.py
Date: 10/10/2025
"""

import logging
from typing import Dict, Any, List, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed

from .pdf_parallel_worker import process_single_page_worker

logger = logging.getLogger(__name__)

# Check dependencies
try:
    # TODO: Implementar módulo RAG completo
    # from app.modules.rag.utils.progress_store import is_cancelled
    HAS_DEPENDENCIES = False  # Temporalmente False hasta implementar RAG
except ImportError as e:
    logger.error(f"❌ Missing dependencies for parallel executor: {e}")
    HAS_DEPENDENCIES = False


class PDFParallelExecutor:
    """
    Executes parallel processing of PDF pages using ProcessPoolExecutor.
    Single responsibility: parallel execution coordination.
    """
    
    def __init__(
        self,
        max_workers: int,
        page_timeout: int,
        log_per_page: bool = True
    ):
        """
        Initialize parallel executor.
        
        Args:
            max_workers: Maximum number of parallel workers
            page_timeout: Timeout per page in seconds
            log_per_page: Enable per-page logging
        """
        if not HAS_DEPENDENCIES:
            raise ImportError("Required dependencies not available for PDFParallelExecutor")
        
        self.max_workers = max_workers
        self.page_timeout = page_timeout
        self.log_per_page = log_per_page
        
        logger.info(f"⚙️ Parallel executor initialized: {max_workers} workers, "
                   f"{page_timeout}s timeout")
    
    def execute_parallel_processing(
        self,
        pdf_path_str: str,
        page_range: List[int],
        strategy: str,
        job_id: Optional[str]
    ) -> Dict[int, Optional[Dict[str, Any]]]:
        """
        Execute the parallel processing using ProcessPoolExecutor.
        
        Args:
            pdf_path_str: PDF file path as string
            page_range: List of page indices to process
            strategy: OCR strategy
            job_id: Job ID for cancellation checking
            
        Returns:
            Dictionary mapping page indices to results
        """
        batch_results = {}
        
        # Use ProcessPoolExecutor for parallel processing
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all pages for processing
            future_to_page = {}
            
            for page_idx in page_range:
                # Check cancellation before submitting each page
                if job_id and is_cancelled(job_id):
                    logger.info(f"🛑 [PARALLEL] Job {job_id} cancelled, skipping page {page_idx + 1}")
                    break
                
                future = executor.submit(
                    process_single_page_worker,
                    pdf_path_str,
                    page_idx,
                    strategy,
                    self.page_timeout,
                    2  # max_retries
                )
                future_to_page[future] = page_idx
            
            if self.log_per_page:
                logger.info(f"📤 [PARALLEL] Submitted {len(future_to_page)} pages for processing")
            
            # Collect results as they complete
            timeout_total = self.page_timeout * len(page_range)
            
            for future in as_completed(future_to_page.keys(), timeout=timeout_total):
                # Check for cancellation during processing
                if job_id and is_cancelled(job_id):
                    logger.info(f"🛑 [PARALLEL] Job {job_id} cancelled, stopping result collection")
                    # Cancel remaining futures
                    for remaining_future in future_to_page.keys():
                        if not remaining_future.done():
                            remaining_future.cancel()
                    break
                
                try:
                    page_idx, result = future.result(timeout=5)  # Short timeout for result retrieval
                    batch_results[page_idx] = result
                    
                    if self.log_per_page:
                        if result:
                            text_len = len(result.get("text", ""))
                            tables_count = len(result.get("tables", []))
                            logger.info(f"✅ [PARALLEL] Page {page_idx + 1} completed: "
                                       f"{text_len} chars, {tables_count} tables")
                        else:
                            logger.warning(f"⚠️ [PARALLEL] Page {page_idx + 1} returned no results")
                    
                except Exception as e:
                    page_idx = future_to_page[future]
                    logger.error(f"❌ [PARALLEL] Page {page_idx + 1} processing failed: {e}")
                    batch_results[page_idx] = None
        
        return batch_results







