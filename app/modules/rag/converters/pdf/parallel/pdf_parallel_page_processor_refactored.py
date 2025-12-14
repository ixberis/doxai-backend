# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_parallel_page_processor_refactored.py

Refactored PDF parallel page processor - clean coordination of specialized components.
Main entry point that maintains backward compatibility while using modular architecture.

Author: Ixchel Beristáin Mendoza
Date: 28/09/2025 - Refactored from 443-line pdf_parallel_page_processor.py
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union, List

from .pdf_batch_coordinator import PDFBatchCoordinatorRefactored as PDFBatchCoordinator
from .pdf_parallel_worker import validate_worker_environment, worker_health_check

logger = logging.getLogger(__name__)

# Check dependencies
try:
    from app.shared.config import settings
    HAS_DEPENDENCIES = True
except ImportError as e:
    logger.error(f"❌ Missing dependencies for parallel processor: {e}")
    HAS_DEPENDENCIES = False


class ParallelPageProcessorRefactored:
    """
    Clean, modular PDF parallel page processor.
    
    Responsibilities:
    1. Maintain backward compatibility API
    2. Coordinate specialized components
    3. Provide unified interface for parallel PDF processing
    
    Delegates actual work to specialized handlers.
    """
    
    def __init__(self):
        """Initialize with specialized components."""
        if not HAS_DEPENDENCIES:
            raise ImportError("Required dependencies not available for ParallelPageProcessorRefactored")
        
        # Initialize batch coordinator with configuration
        self.batch_coordinator = PDFBatchCoordinator(
            max_workers=getattr(settings.ocr, 'max_workers', 4),
            batch_size=getattr(settings.ocr, 'batch_pages', 10),
            page_timeout=getattr(settings.ocr, 'page_timeout_sec', 120)
        )
        
        # Configuration from settings (for backward compatibility)
        self.max_workers = self.batch_coordinator.max_workers
        self.batch_pages = self.batch_coordinator.batch_size
        self.page_timeout = self.batch_coordinator.page_timeout
        
        # Logging configuration
        self.log_per_page = getattr(settings.logging, 'ocr_per_page', True)
        self.log_timing = getattr(settings.logging, 'ocr_timing_details', True)
        self.log_performance = getattr(settings.logging, 'performance_metrics', True)
        
        # Performance tracking (for backward compatibility)
        self.batch_times = []
        self.page_times = []
        
        logger.debug(f"🚀 Parallel processor initialized with {self.max_workers} workers")
    
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
        
        Maintains exact same API as original implementation.
        
        Args:
            pdf_path: Path to PDF file
            start_page: Starting page index (0-indexed)
            end_page: Ending page index (exclusive)
            strategy: OCR strategy for all pages
            job_id: Job ID for cancellation checking
            
        Returns:
            Dictionary with consolidated batch results
        """
        result = self.batch_coordinator.process_batch_parallel(
            pdf_path, start_page, end_page, strategy, job_id
        )
        
        # Update legacy performance tracking for backward compatibility
        if "batch_time_seconds" in result:
            self.batch_times.append(result["batch_time_seconds"])
        
        return result
    
    def process_document_parallel(
        self,
        pdf_path: Union[str, Path],
        total_pages: int,
        job_id: Optional[str] = None
    ) -> Optional[Dict[str, Union[str, List]]]:
        """
        Process entire document using parallel batch processing.
        
        Maintains exact same API as original implementation.
        
        Args:
            pdf_path: Path to PDF file
            total_pages: Total number of pages in document
            job_id: Job ID for cancellation checking
            
        Returns:
            Dictionary with consolidated document results
        """
        result = self.batch_coordinator.process_document_in_batches(
            pdf_path, total_pages, job_id, "hi_res"
        )
        
        # Extract performance data for backward compatibility
        if result and "performance_summary" in result:
            perf = result["performance_summary"]
            if "timing_stats" in perf:
                timing = perf["timing_stats"]
                if timing.get("avg_batch_time"):
                    self.batch_times.append(timing["avg_batch_time"])
                if timing.get("avg_page_time"):
                    self.page_times.append(timing["avg_page_time"])
        
        return result
    
    def process_pages_parallel(self, *args, **kwargs):
        """
        Legacy compatibility wrapper for process_document_parallel.
        
        Maintains exact same API as original implementation.
        This method maintains backward compatibility with existing code
        that calls process_pages_parallel instead of process_document_parallel.
        """
        return self.process_document_parallel(*args, **kwargs)
    
    def _empty_batch_result(self) -> Dict[str, Any]:
        """
        Return empty batch result structure.
        
        Maintains exact same API as original implementation.
        """
        return {
            "text": "",
            "tables": [],
            "forms": [],
            "md_size_bytes": 0,
            "no_text_extracted": True,
            "pages_processed": 0,
            "processing_mode": "parallel_cancelled"
        }
    
    def _calculate_speedup(self) -> float:
        """
        Calculate theoretical speedup based on parallel processing.
        
        Maintains exact same API as original implementation.
        
        Returns:
            Speedup factor compared to sequential processing
        """
        if not self.batch_times or not self.page_times:
            return 1.0
        
        # Use performance tracker for accurate calculation
        performance_summary = self.batch_coordinator.performance_tracker.get_performance_summary()
        
        if "performance_metrics" in performance_summary:
            actual_speedup = performance_summary["performance_metrics"].get("actual_speedup", 1.0)
            return actual_speedup
        
        # Fallback to original calculation for backward compatibility
        avg_page_time = sum(self.page_times) / len(self.page_times) if self.page_times else 0
        avg_batch_time = sum(self.batch_times) / len(self.batch_times) if self.batch_times else 0
        
        if avg_batch_time > 0 and avg_page_time > 0:
            pages_per_batch = self.batch_pages
            sequential_batch_time = avg_page_time * pages_per_batch
            return sequential_batch_time / avg_batch_time
        
        return self.max_workers  # Theoretical maximum
    
    # New methods that expose additional functionality
    def validate_parallel_environment(self) -> Dict[str, Any]:
        """
        Validate that the parallel processing environment is ready.
        
        Returns:
            Dictionary with environment validation results
        """
        try:
            # Validate worker environment
            worker_validation = validate_worker_environment()
            
            # Get coordinator status
            coordinator_status = self.batch_coordinator.get_coordinator_status()
            
            # Perform worker health check
            health_check = worker_health_check(0)
            
            return {
                "environment_ready": True,
                "worker_validation": worker_validation,
                "coordinator_status": coordinator_status,
                "health_check": health_check,
                "max_workers": self.max_workers,
                "batch_size": self.batch_pages
            }
            
        except Exception as e:
            logger.error(f"❌ Environment validation failed: {e}")
            return {
                "environment_ready": False,
                "error": str(e)
            }
    
    def get_processing_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive processing statistics.
        
        Returns:
            Dictionary with processing statistics
        """
        performance_summary = self.batch_coordinator.performance_tracker.get_performance_summary()
        consolidation_stats = self.batch_coordinator.result_consolidator.get_consolidation_statistics()
        
        # Add legacy compatibility stats
        legacy_stats = {
            "batch_times": self.batch_times[-10:],  # Last 10 for memory efficiency
            "page_times": self.page_times[-10:],
            "average_batch_time": sum(self.batch_times) / len(self.batch_times) if self.batch_times else 0,
            "average_page_time": sum(self.page_times) / len(self.page_times) if self.page_times else 0,
            "calculated_speedup": self._calculate_speedup()
        }
        
        return {
            "performance_summary": performance_summary,
            "consolidation_stats": consolidation_stats,
            "legacy_compatibility": legacy_stats,
            "configuration": {
                "max_workers": self.max_workers,
                "batch_pages": self.batch_pages,
                "page_timeout": self.page_timeout
            }
        }
    
    def reset_processor(self):
        """
        Reset processor statistics and state.
        """
        # Reset coordinator
        self.batch_coordinator.reset_coordinator()
        
        # Reset legacy compatibility data
        self.batch_times.clear()
        self.page_times.clear()
        
        logger.info("🔄 Parallel processor reset completed")


# Global processor instance for backward compatibility
_parallel_processor_instance = None

def get_parallel_processor() -> ParallelPageProcessorRefactored:
    """
    Get singleton parallel processor instance.
    
    Maintains exact same API as original implementation.
    """
    global _parallel_processor_instance
    if _parallel_processor_instance is None:
        _parallel_processor_instance = ParallelPageProcessorRefactored()
    return _parallel_processor_instance


# Convenience functions for backward compatibility
def process_batch_parallel(pdf_path: Union[str, Path], start_page: int, end_page: int, **kwargs) -> Dict[str, Any]:
    """
    Convenience function for parallel batch processing.
    
    Maintains exact same API as original implementation.
    """
    return get_parallel_processor().process_batch_parallel(pdf_path, start_page, end_page, **kwargs)


def process_document_parallel(pdf_path: Union[str, Path], total_pages: int, **kwargs) -> Optional[Dict[str, Union[str, List]]]:
    """
    Convenience function for parallel document processing.
    
    Maintains exact same API as original implementation.
    """
    return get_parallel_processor().process_document_parallel(pdf_path, total_pages, **kwargs)


# Worker function import for backward compatibility
from .pdf_parallel_worker import process_single_page_worker


# Export main functions - same as original
__all__ = [
    'ParallelPageProcessorRefactored',
    'get_parallel_processor',
    'process_batch_parallel',
    'process_document_parallel',
    'process_single_page_worker'  # Export worker for testing
]

# Alias for backward compatibility
ParallelPageProcessor = ParallelPageProcessorRefactored






