# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_processing_metrics.py

Metrics collection and reporting for PDF processing operations.
Single responsibility: metrics tracking and statistics management.

Author: Ixchel Beristáin Mendoza  
Date: 28/09/2025 - Refactored from pdf_cached_page_processor.py
"""

from typing import Dict, Any, Set
from dataclasses import dataclass, field
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ProcessingMetrics:
    """
    Data class to track processing metrics during PDF operations.
    """
    total_pages: int = 0
    pages_to_process: int = 0
    already_processed: int = 0 
    remaining_pages: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    processing_errors: int = 0
    batches_persisted: int = 0
    processed_pages: Set[int] = field(default_factory=set)
    error_pages: Set[int] = field(default_factory=set)
    
    def record_cache_hit(self, page_num: int):
        """Record a successful cache hit."""
        self.cache_hits += 1
        logger.debug(f"📦 Cache hit recorded for page {page_num}")
    
    def record_cache_miss(self, page_num: int):
        """Record a cache miss."""
        self.cache_misses += 1
        logger.debug(f"💨 Cache miss recorded for page {page_num}")
    
    def record_page_processed(self, page_num: int):
        """Record a successfully processed page."""
        self.processed_pages.add(page_num)
        logger.debug(f"✅ Page {page_num} processing recorded")
    
    def record_processing_error(self, page_num: int, error: str):
        """Record a processing error for a page."""
        self.processing_errors += 1
        self.error_pages.add(page_num)
        logger.warning(f"❌ Processing error recorded for page {page_num}: {error}")
    
    def record_batch_persisted(self):
        """Record a successful batch persistence."""
        self.batches_persisted += 1
        logger.info(f"💾 Batch persistence recorded (total: {self.batches_persisted})")
    
    def get_cache_hit_rate(self) -> float:
        """Calculate cache hit rate as percentage."""
        total_requests = self.cache_hits + self.cache_misses
        if total_requests == 0:
            return 0.0
        return (self.cache_hits / total_requests) * 100
    
    def get_error_rate(self) -> float:
        """Calculate error rate as percentage."""
        if self.pages_to_process == 0:
            return 0.0
        return (self.processing_errors / self.pages_to_process) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary format."""
        return {
            'total_pages': self.total_pages,
            'pages_to_process': self.pages_to_process,
            'already_processed': self.already_processed,
            'remaining_pages': self.remaining_pages,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'processing_errors': self.processing_errors,
            'batches_persisted': self.batches_persisted,
            'cache_hit_rate': round(self.get_cache_hit_rate(), 2),
            'error_rate': round(self.get_error_rate(), 2),
            'processed_page_count': len(self.processed_pages),
            'error_page_count': len(self.error_pages)
        }


class PDFProcessingMetricsCollector:
    """
    Collects and manages processing metrics for PDF operations.
    Single responsibility: metrics collection and reporting.
    """
    
    def __init__(self):
        self.metrics = ProcessingMetrics()
    
    def initialize_metrics(
        self, 
        total_pages: int, 
        pages_to_process: Set[int], 
        already_processed: Set[int]
    ):
        """
        Initialize metrics with document and job information.
        
        Args:
            total_pages: Total pages in PDF
            pages_to_process: Set of page numbers to process
            already_processed: Set of already processed pages
        """
        remaining = pages_to_process - already_processed
        
        self.metrics.total_pages = total_pages
        self.metrics.pages_to_process = len(pages_to_process)
        self.metrics.already_processed = len(already_processed)
        self.metrics.remaining_pages = len(remaining)
        
        logger.info(f"📊 Metrics initialized: {self.metrics.remaining_pages} pages remaining "
                   f"({self.metrics.already_processed} already processed)")
    
    def record_page_operation(
        self, 
        page_num: int, 
        operation_type: str, 
        success: bool = True, 
        error: str = None
    ):
        """
        Record a page-level operation.
        
        Args:
            page_num: Page number processed
            operation_type: Type of operation (cache_hit, cache_miss, processing, etc.)
            success: Whether operation was successful
            error: Error message if operation failed
        """
        if operation_type == "cache_hit":
            self.metrics.record_cache_hit(page_num)
        elif operation_type == "cache_miss":
            self.metrics.record_cache_miss(page_num)
        
        if success:
            self.metrics.record_page_processed(page_num)
        elif error:
            self.metrics.record_processing_error(page_num, error)
    
    def record_batch_persistence(self):
        """Record a successful batch persistence operation."""
        self.metrics.record_batch_persisted()
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current metrics as dictionary."""
        return self.metrics.to_dict()
    
    def get_summary_report(self, job_id: str, pdf_path: Path) -> str:
        """
        Generate a human-readable summary report.
        
        Args:
            job_id: Job identifier
            pdf_path: Path to PDF file
            
        Returns:
            Formatted summary string
        """
        metrics_dict = self.metrics.to_dict()
        
        return (
            f"📋 Processing Summary - Job {job_id}\n"
            f"📄 File: {pdf_path.name}\n"
            f"📊 Pages: {metrics_dict['processed_page_count']}/{metrics_dict['pages_to_process']} processed\n"
            f"📦 Cache: {metrics_dict['cache_hits']} hits, {metrics_dict['cache_misses']} misses "
            f"({metrics_dict['cache_hit_rate']}% hit rate)\n"
            f"❌ Errors: {metrics_dict['processing_errors']} ({metrics_dict['error_rate']}% error rate)\n"
            f"💾 Batches persisted: {metrics_dict['batches_persisted']}"
        )






