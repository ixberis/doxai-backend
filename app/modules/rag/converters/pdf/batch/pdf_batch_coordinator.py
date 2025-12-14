# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_batch_coordinator_refactored.py

Refactored batch coordination for PDF processing with smaller, focused modules.
Single responsibility: orchestrating parallel batch processing operations.

Author: Refactored from pdf_batch_coordinator.py
Date: 10/10/2025
"""

import logging
import time
import math
from pathlib import Path
from typing import Dict, Any, Optional, Union

from .pdf_batch_config_manager import PDFBatchConfigManager
from .pdf_parallel_executor import PDFParallelExecutor
from .pdf_batch_result_factory import PDFBatchResultFactory
from .pdf_result_consolidator import PDFResultConsolidator
from .pdf_parallel_performance import PDFParallelPerformanceTracker

logger = logging.getLogger(__name__)

# Check dependencies
try:
    # TODO: Implementar módulo RAG completo
    # from app.modules.rag.utils.progress_store import is_cancelled
    HAS_DEPENDENCIES = False  # Temporalmente False hasta implementar RAG
except ImportError as e:
    logger.error(f"❌ Missing dependencies for batch coordinator: {e}")
    HAS_DEPENDENCIES = False


class PDFBatchCoordinatorRefactored:
    """
    Coordinates parallel batch processing of PDF pages.
    Single responsibility: orchestrating specialized components for batch processing.
    """
    
    def __init__(
        self, 
        max_workers: Optional[int] = None,
        batch_size: Optional[int] = None,
        page_timeout: Optional[int] = None
    ):
        """
        Initialize batch coordinator with specialized components.
        
        Args:
            max_workers: Maximum number of parallel workers (uses config default if None)
            batch_size: Pages per batch (uses config default if None)
            page_timeout: Timeout per page in seconds (uses config default if None)
        """
        if not HAS_DEPENDENCIES:
            raise ImportError("Required dependencies not available for PDFBatchCoordinatorRefactored")
        
        # Initialize configuration manager
        self.config_manager = PDFBatchConfigManager(max_workers, batch_size, page_timeout)
        
        # Get configuration values
        config = self.config_manager.get_processing_config()
        self.max_workers = config["max_workers"]
        self.batch_size = config["batch_size"]
        self.page_timeout = config["page_timeout"]
        
        # Initialize parallel executor
        self.executor = PDFParallelExecutor(
            self.max_workers,
            self.page_timeout,
            self.config_manager.should_log_per_page()
        )
        
        # Initialize result factory
        self.result_factory = PDFBatchResultFactory()
        
        # Initialize consolidator and performance tracker
        self.result_consolidator = PDFResultConsolidator()
        self.performance_tracker = PDFParallelPerformanceTracker()
        
        # Configure performance tracker
        self.performance_tracker.configure_for_job(self.max_workers, self.batch_size)
        
        logger.info(f"🚀 Batch coordinator (refactored) initialized: {self.max_workers} workers, "
                   f"{self.batch_size} pages/batch, {self.page_timeout}s timeout")
    
    def process_batch_parallel(
        self,
        pdf_path: Union[str, Path],
        start_page: int,
        end_page: int,
        strategy: str = "hi_res",
        job_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a batch of PDF pages in parallel.
        
        Args:
            pdf_path: Path to PDF file
            start_page: Starting page index (0-indexed)
            end_page: Ending page index (exclusive)
            strategy: OCR strategy for all pages
            job_id: Job ID for cancellation checking
            
        Returns:
            Dictionary with consolidated batch results
        """
        batch_start_time = time.time()
        pdf_path_str = str(pdf_path)
        page_range = list(range(start_page, end_page))
        num_pages = len(page_range)
        
        if self.config_manager.should_log_per_page():
            logger.info(f"🚀 [PARALLEL] Starting batch processing: pages {start_page + 1}-{end_page} "
                       f"with {self.max_workers} workers")
        
        # Check for job cancellation before starting
        if job_id and is_cancelled(job_id):
            logger.info(f"🛑 [PARALLEL] Job {job_id} cancelled before batch start")
            return self.result_factory.create_cancelled_batch_result(start_page, end_page)
        
        batch_results = {}
        completed_count = 0
        
        try:
            # Execute parallel processing
            batch_results = self.executor.execute_parallel_processing(
                pdf_path_str, page_range, strategy, job_id
            )
            completed_count = len([r for r in batch_results.values() if r is not None])
            
        except Exception as e:
            logger.error(f"❌ [PARALLEL] Batch processing error: {e}")
            return self.result_factory.create_error_batch_result(start_page, end_page, str(e))
        
        # Consolidate results
        consolidated = self.result_consolidator.consolidate_batch_results(
            batch_results, start_page, end_page
        )
        
        # Record performance metrics
        batch_time = time.time() - batch_start_time
        batch_number = 0  # Will be set by caller if needed
        total_batches = 1  # Will be set by caller if needed
        
        performance_metrics = self.performance_tracker.record_batch_completion(
            batch_time, completed_count, batch_number, total_batches
        )
        
        # Add batch metadata using factory
        batch_metadata = self.result_factory.create_batch_metadata(
            batch_time, completed_count, num_pages, performance_metrics
        )
        consolidated.update(batch_metadata)
        
        if self.config_manager.should_log_timing() or self.config_manager.should_log_performance():
            avg_time_per_page = batch_time / max(1, completed_count)
            logger.info(f"📊 [PARALLEL] Batch completed: {completed_count}/{num_pages} pages "
                       f"in {batch_time:.2f}s (avg: {avg_time_per_page:.2f}s/page)")
        
        return consolidated
    
    def process_document_in_batches(
        self,
        pdf_path: Union[str, Path],
        total_pages: int,
        job_id: Optional[str] = None,
        strategy: str = "hi_res"
    ) -> Dict[str, Union[str, list, int, bool]]:
        """
        Process entire document using parallel batch processing.
        
        Args:
            pdf_path: Path to PDF file
            total_pages: Total number of pages in document
            job_id: Job ID for cancellation checking
            strategy: OCR strategy to use
            
        Returns:
            Dictionary with consolidated document results
        """
        if self.config_manager.should_log_performance():
            logger.info(f"🚀 [PARALLEL-DOC] Starting parallel document processing: "
                       f"{total_pages} pages in batches of {self.batch_size}")
        
        batch_results = []
        total_batches = math.ceil(total_pages / self.batch_size)
        
        # Process document in batches
        for batch_num in range(total_batches):
            # Check for cancellation before each batch
            if job_id and is_cancelled(job_id):
                logger.info(f"🛑 [PARALLEL-DOC] Job {job_id} cancelled after {batch_num} batches")
                break
            
            start_page = batch_num * self.batch_size
            end_page = min((batch_num + 1) * self.batch_size, total_pages)
            
            # Process batch
            batch_result = self.process_batch_parallel(
                pdf_path, start_page, end_page, strategy, job_id
            )
            
            if batch_result:
                batch_results.append(batch_result)
                
                # Log batch completion with performance metrics
                if self.config_manager.should_log_performance() and batch_num > 0:
                    self.performance_tracker.log_performance_update(batch_num, total_batches)
                
                # Progress reporting
                progress = (batch_num + 1) / total_batches
                pages_processed = sum(b.get("pages_processed", 0) for b in batch_results)
                
                logger.info(f"📊 [PARALLEL-DOC] Progress: {progress:.1%} "
                           f"({batch_num + 1}/{total_batches} batches, {pages_processed}/{total_pages} pages)")
        
        # Consolidate all batch results into final document
        if not batch_results:
            logger.error("❌ [PARALLEL-DOC] No batches completed successfully")
            return self.result_consolidator.create_empty_result("no_batches_completed", "parallel")
        
        final_result = self.result_consolidator.consolidate_document_results(
            batch_results, total_pages, "parallel"
        )
        
        # Add document-level performance metrics
        performance_summary = self.performance_tracker.get_performance_summary()
        final_result["performance_summary"] = performance_summary
        
        if self.config_manager.should_log_performance():
            stats = final_result.get("processing_stats", {})
            perf = performance_summary.get("performance_metrics", {})
            
            logger.info(f"🎯 [PARALLEL-DOC] Document processing completed: "
                       f"{len(final_result.get('text', ''))} chars, "
                       f"{stats.get('success_rate', 0):.1%} success rate, "
                       f"{perf.get('actual_speedup', 1):.1f}x speedup")
        
        return final_result
    
    def get_coordinator_status(self) -> Dict[str, Any]:
        """
        Get current coordinator status and statistics.
        
        Returns:
            Dictionary with coordinator status
        """
        performance_summary = self.performance_tracker.get_performance_summary()
        consolidation_stats = self.result_consolidator.get_consolidation_statistics()
        
        return {
            "configuration": self.config_manager.get_processing_config(),
            "logging_config": self.config_manager.get_logging_config(),
            "performance_summary": performance_summary,
            "consolidation_stats": consolidation_stats,
            "system_ready": True
        }
    
    def reset_coordinator(self):
        """Reset coordinator statistics and state."""
        self.performance_tracker.reset_metrics()
        self.result_consolidator.reset_statistics()
        
        logger.info("🔄 Batch coordinator (refactored) reset")







