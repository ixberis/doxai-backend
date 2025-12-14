# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_parallel_performance.py

Performance tracking and metrics for PDF parallel processing.
Single responsibility: performance monitoring, ETA calculation, and speedup metrics.

Author: Ixchel Beristáin Mendoza
Date: 28/09/2025 - Refactored from pdf_parallel_page_processor.py
"""

import time
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class ProcessingMetrics:
    """Data class for tracking processing performance metrics."""
    batch_times: List[float] = field(default_factory=list)
    page_times: List[float] = field(default_factory=list)
    pages_per_batch: int = 10
    max_workers: int = 4
    total_pages_processed: int = 0
    start_time: Optional[float] = None
    
    def __post_init__(self):
        if self.start_time is None:
            self.start_time = time.time()


class PDFParallelPerformanceTracker:
    """
    Tracks performance metrics for PDF parallel processing operations.
    Single responsibility: performance monitoring and analysis.
    """
    
    def __init__(self, max_history: int = 100):
        """
        Initialize performance tracker.
        
        Args:
            max_history: Maximum number of historical entries to keep
        """
        self.max_history = max_history
        self.metrics = ProcessingMetrics()
        
        # Use deque for efficient rolling window
        self.recent_batch_times = deque(maxlen=max_history)
        self.recent_page_times = deque(maxlen=max_history)
        
        # ETA calculation
        self.eta_window_size = min(5, max_history)
        self.last_progress_update = time.time()
        
        logger.debug(f"📊 Performance tracker initialized with {max_history} history limit")
    
    def record_batch_completion(
        self, 
        batch_time: float, 
        pages_processed: int,
        batch_number: int,
        total_batches: int
    ) -> Dict[str, float]:
        """
        Record completion of a batch and calculate metrics.
        
        Args:
            batch_time: Time taken for batch processing
            pages_processed: Number of pages processed in batch
            batch_number: Current batch number (0-indexed)
            total_batches: Total number of batches
            
        Returns:
            Dictionary with calculated metrics
        """
        self.metrics.batch_times.append(batch_time)
        self.recent_batch_times.append(batch_time)
        self.metrics.total_pages_processed += pages_processed
        
        # Calculate average page time for this batch
        if pages_processed > 0:
            avg_page_time_this_batch = batch_time / pages_processed
            self.metrics.page_times.append(avg_page_time_this_batch)
            self.recent_page_times.append(avg_page_time_this_batch)
        
        # Calculate metrics
        metrics = self._calculate_current_metrics(batch_number, total_batches)
        
        logger.debug(f"📊 Batch {batch_number + 1} metrics: {batch_time:.2f}s, "
                    f"{pages_processed} pages, ETA: {metrics.get('eta_minutes', 0):.1f}m")
        
        return metrics
    
    def _calculate_current_metrics(self, batch_number: int, total_batches: int) -> Dict[str, float]:
        """
        Calculate current performance metrics.
        
        Args:
            batch_number: Current batch number (0-indexed)
            total_batches: Total number of batches
            
        Returns:
            Dictionary with performance metrics
        """
        current_time = time.time()
        elapsed_time = current_time - self.metrics.start_time
        
        # Basic metrics
        completed_batches = batch_number + 1
        remaining_batches = total_batches - completed_batches
        progress = completed_batches / total_batches if total_batches > 0 else 0
        
        # Average times
        avg_batch_time = self._get_rolling_average(self.recent_batch_times)
        avg_page_time = self._get_rolling_average(self.recent_page_times)
        
        # ETA calculation
        eta_seconds = remaining_batches * avg_batch_time if avg_batch_time > 0 else 0
        eta_minutes = eta_seconds / 60
        
        # Throughput metrics
        pages_per_second = self.metrics.total_pages_processed / elapsed_time if elapsed_time > 0 else 0
        batches_per_hour = (completed_batches / elapsed_time) * 3600 if elapsed_time > 0 else 0
        
        # Efficiency metrics
        theoretical_speedup = self._calculate_theoretical_speedup()
        actual_speedup = self._calculate_actual_speedup()
        efficiency = (actual_speedup / theoretical_speedup) if theoretical_speedup > 0 else 0
        
        return {
            "progress": progress,
            "elapsed_time": elapsed_time,
            "eta_seconds": eta_seconds,
            "eta_minutes": eta_minutes,
            "avg_batch_time": avg_batch_time,
            "avg_page_time": avg_page_time,
            "pages_per_second": pages_per_second,
            "batches_per_hour": batches_per_hour,
            "theoretical_speedup": theoretical_speedup,
            "actual_speedup": actual_speedup,
            "efficiency": efficiency,
            "completed_batches": completed_batches,
            "remaining_batches": remaining_batches
        }
    
    def _get_rolling_average(self, values: deque) -> float:
        """
        Calculate rolling average from recent values.
        
        Args:
            values: Deque of recent values
            
        Returns:
            Rolling average
        """
        if not values:
            return 0.0
        
        # Use recent values for ETA (more responsive to current performance)
        recent_values = list(values)[-self.eta_window_size:]
        return sum(recent_values) / len(recent_values)
    
    def _calculate_theoretical_speedup(self) -> float:
        """
        Calculate theoretical maximum speedup based on worker count.
        
        Returns:
            Theoretical speedup factor
        """
        return min(self.metrics.max_workers, self.metrics.pages_per_batch)
    
    def _calculate_actual_speedup(self) -> float:
        """
        Calculate actual speedup based on measured performance.
        
        Returns:
            Actual speedup factor
        """
        if not self.metrics.page_times or not self.metrics.batch_times:
            return 1.0
        
        avg_page_time = sum(self.metrics.page_times) / len(self.metrics.page_times)
        avg_batch_time = sum(self.metrics.batch_times) / len(self.metrics.batch_times)
        
        if avg_batch_time > 0 and avg_page_time > 0:
            # Calculate how much time sequential processing would take
            sequential_batch_time = avg_page_time * self.metrics.pages_per_batch
            return sequential_batch_time / avg_batch_time
        
        return 1.0
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive performance summary.
        
        Returns:
            Dictionary with performance summary
        """
        if not self.metrics.batch_times:
            return {"status": "no_data", "message": "No batches completed yet"}
        
        current_time = time.time()
        total_elapsed = current_time - self.metrics.start_time
        
        # Calculate statistics
        batch_times = list(self.metrics.batch_times)
        page_times = list(self.metrics.page_times)
        
        summary = {
            "processing_stats": {
                "total_batches": len(batch_times),
                "total_pages": self.metrics.total_pages_processed,
                "total_time": total_elapsed,
                "avg_pages_per_batch": self.metrics.total_pages_processed / len(batch_times) if batch_times else 0
            },
            "timing_stats": {
                "avg_batch_time": sum(batch_times) / len(batch_times) if batch_times else 0,
                "min_batch_time": min(batch_times) if batch_times else 0,
                "max_batch_time": max(batch_times) if batch_times else 0,
                "avg_page_time": sum(page_times) / len(page_times) if page_times else 0
            },
            "performance_metrics": {
                "theoretical_speedup": self._calculate_theoretical_speedup(),
                "actual_speedup": self._calculate_actual_speedup(),
                "efficiency": 0.0,  # Will be calculated below
                "pages_per_second": self.metrics.total_pages_processed / total_elapsed if total_elapsed > 0 else 0
            }
        }
        
        # Calculate efficiency
        theoretical = summary["performance_metrics"]["theoretical_speedup"]
        actual = summary["performance_metrics"]["actual_speedup"]
        summary["performance_metrics"]["efficiency"] = (actual / theoretical) if theoretical > 0 else 0
        
        return summary
    
    def log_performance_update(
        self, 
        batch_number: int, 
        total_batches: int,
        force_log: bool = False
    ):
        """
        Log performance update if enough time has passed.
        
        Args:
            batch_number: Current batch number
            total_batches: Total number of batches
            force_log: Force logging regardless of time interval
        """
        current_time = time.time()
        
        # Log every 30 seconds or on force
        if force_log or (current_time - self.last_progress_update) >= 30:
            metrics = self._calculate_current_metrics(batch_number, total_batches)
            
            logger.info(f"📈 Performance Update - Batch {batch_number + 1}/{total_batches} "
                       f"({metrics['progress']:.1%} complete)")
            logger.info(f"📊 Timing: {metrics['avg_batch_time']:.2f}s/batch, "
                       f"{metrics['avg_page_time']:.2f}s/page, ETA: {metrics['eta_minutes']:.1f}m")
            logger.info(f"🚀 Efficiency: {metrics['efficiency']:.1%} "
                       f"(actual: {metrics['actual_speedup']:.1f}x, "
                       f"theoretical: {metrics['theoretical_speedup']:.1f}x)")
            
            self.last_progress_update = current_time
    
    def reset_metrics(self):
        """Reset all performance metrics."""
        self.metrics = ProcessingMetrics()
        self.recent_batch_times.clear()
        self.recent_page_times.clear()
        self.last_progress_update = time.time()
        
        logger.debug("📊 Performance metrics reset")
    
    def configure_for_job(self, max_workers: int, pages_per_batch: int):
        """
        Configure tracker for a specific job.
        
        Args:
            max_workers: Number of parallel workers
            pages_per_batch: Pages processed per batch
        """
        self.metrics.max_workers = max_workers
        self.metrics.pages_per_batch = pages_per_batch
        
        logger.debug(f"📊 Configured for {max_workers} workers, {pages_per_batch} pages/batch")
    
    # ========== Backward Compatibility Wrappers ==========
    def start_tracking(self, total_pages: int):
        """
        Backward compatibility wrapper for tests.
        Maintains the old method name expected by legacy tests.
        
        Args:
            total_pages: Total number of pages to track
        """
        # Initialize tracking state
        self.total_pages = total_pages
        self._started = True
        self._completed = 0
        self.metrics.start_time = time.time()
        logger.debug(f"📊 Started tracking for {total_pages} pages")
    
    def stop_tracking(self):
        """
        Backward compatibility wrapper for stopping tracking.
        Maintains the old method name expected by legacy tests.
        """
        self._started = False
        logger.debug("📊 Stopped tracking")
    
    def mark_page_done(self, page_number: Optional[int] = None):
        """
        Backward compatibility wrapper for marking a page as completed.
        
        Args:
            page_number: Page number that was completed (optional)
        """
        if not hasattr(self, "_completed"):
            self._completed = 0
        self._completed += 1
        logger.debug(f"📊 Marked page {page_number or self._completed} as done")






