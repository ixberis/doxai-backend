# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_batch_config_manager.py

Configuration management for PDF batch processing.
Single responsibility: managing configuration and logging settings.

Author: Refactored from pdf_batch_coordinator.py
Date: 10/10/2025
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Check dependencies
try:
    from app.shared.config import settings
    HAS_DEPENDENCIES = True
except ImportError as e:
    logger.error(f"❌ Missing dependencies for batch config manager: {e}")
    HAS_DEPENDENCIES = False


class PDFBatchConfigManager:
    """
    Manages configuration settings for PDF batch processing.
    Single responsibility: configuration and logging settings management.
    """
    
    def __init__(
        self,
        max_workers: Optional[int] = None,
        batch_size: Optional[int] = None,
        page_timeout: Optional[int] = None
    ):
        """
        Initialize configuration manager.
        
        Args:
            max_workers: Maximum number of parallel workers (uses config default if None)
            batch_size: Pages per batch (uses config default if None)
            page_timeout: Timeout per page in seconds (uses config default if None)
        """
        if not HAS_DEPENDENCIES:
            raise ImportError("Required dependencies not available for PDFBatchConfigManager")
        
        # Processing configuration
        self.max_workers = max_workers or getattr(settings.ocr, 'max_workers', 4)
        self.batch_size = batch_size or getattr(settings.ocr, 'batch_pages', 10)
        self.page_timeout = page_timeout or getattr(settings.ocr, 'page_timeout_sec', 120)
        
        # Logging configuration
        self.log_per_page = getattr(settings.logging, 'ocr_per_page', True)
        self.log_timing = getattr(settings.logging, 'ocr_timing_details', True)
        self.log_performance = getattr(settings.logging, 'performance_metrics', True)
        
        logger.info(f"⚙️ Batch config initialized: {self.max_workers} workers, "
                   f"{self.batch_size} pages/batch, {self.page_timeout}s timeout")
    
    def get_processing_config(self) -> dict:
        """Get processing configuration as dictionary."""
        return {
            "max_workers": self.max_workers,
            "batch_size": self.batch_size,
            "page_timeout": self.page_timeout
        }
    
    def get_logging_config(self) -> dict:
        """Get logging configuration as dictionary."""
        return {
            "log_per_page": self.log_per_page,
            "log_timing": self.log_timing,
            "log_performance": self.log_performance
        }
    
    def should_log_per_page(self) -> bool:
        """Check if per-page logging is enabled."""
        return self.log_per_page
    
    def should_log_timing(self) -> bool:
        """Check if timing details logging is enabled."""
        return self.log_timing
    
    def should_log_performance(self) -> bool:
        """Check if performance metrics logging is enabled."""
        return self.log_performance







