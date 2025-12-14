# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_batch_result_factory.py

Factory for creating PDF batch processing result structures.
Single responsibility: creating standardized result dictionaries.

Author: Refactored from pdf_batch_coordinator.py
Date: 10/10/2025
"""

from typing import Dict, Any


class PDFBatchResultFactory:
    """
    Factory for creating standardized batch result structures.
    Single responsibility: result structure creation.
    """
    
    @staticmethod
    def create_cancelled_batch_result(start_page: int, end_page: int) -> Dict[str, Any]:
        """
        Create result structure for cancelled batch.
        
        Args:
            start_page: Starting page index (0-indexed)
            end_page: Ending page index (exclusive)
            
        Returns:
            Dictionary with cancelled batch result structure
        """
        return {
            "text": "",
            "tables": [],
            "forms": [],
            "md_size_bytes": 0,
            "no_text_extracted": True,
            "pages_processed": 0,
            "pages_requested": end_page - start_page,
            "processing_mode": "parallel_cancelled",
            "page_range": f"{start_page + 1}-{end_page}"
        }
    
    @staticmethod
    def create_error_batch_result(start_page: int, end_page: int, error: str) -> Dict[str, Any]:
        """
        Create result structure for failed batch.
        
        Args:
            start_page: Starting page index (0-indexed)
            end_page: Ending page index (exclusive)
            error: Error message
            
        Returns:
            Dictionary with error batch result structure
        """
        return {
            "text": "",
            "tables": [],
            "forms": [],
            "md_size_bytes": 0,
            "no_text_extracted": True,
            "pages_processed": 0,
            "pages_requested": end_page - start_page,
            "processing_mode": "parallel_error",
            "page_range": f"{start_page + 1}-{end_page}",
            "error": error
        }
    
    @staticmethod
    def create_batch_metadata(
        batch_time: float,
        completed_count: int,
        num_pages: int,
        performance_metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create batch metadata structure.
        
        Args:
            batch_time: Time taken to process batch
            completed_count: Number of pages successfully processed
            num_pages: Total number of pages requested
            performance_metrics: Performance metrics dictionary
            
        Returns:
            Dictionary with batch metadata
        """
        return {
            "batch_time_seconds": batch_time,
            "pages_processed": completed_count,
            "pages_requested": num_pages,
            "processing_mode": "parallel",
            "performance_metrics": performance_metrics
        }







