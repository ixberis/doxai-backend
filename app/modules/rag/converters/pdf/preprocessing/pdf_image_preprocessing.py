# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_image_preprocessing_refactored.py

Refactored PDF image preprocessing - clean interface with backward compatibility.
Main entry point that orchestrates specialized components.

Author: Ixchel Beristáin Mendoza
Date: 28/09/2025 - Refactored from 385-line pdf_image_preprocessing.py
"""

import logging
from pathlib import Path
from typing import Optional, Union
import numpy as np

from .pdf_preprocessing_coordinator import PDFPreprocessingCoordinator

logger = logging.getLogger(__name__)


class ImagePreprocessorRefactored:
    """
    Clean, modular image preprocessor for PDF pages.
    
    Responsibilities:
    1. Maintain backward compatibility API
    2. Coordinate specialized components  
    3. Provide unified interface
    
    Delegates actual work to specialized handlers.
    """
    
    def __init__(self):
        """Initialize with coordinator component."""
        self.coordinator = PDFPreprocessingCoordinator()
    
    def preprocess_pdf_page(
        self, 
        pdf_path: Union[str, Path], 
        page_num: int,
        target_dpi: Optional[int] = None,
        timeout_sec: Optional[int] = None
    ) -> Optional[np.ndarray]:
        """
        Preprocess a single PDF page for optimal OCR.
        
        Maintains exact same API as original implementation.
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number (0-indexed)
            target_dpi: Override DPI (uses config default if None)
            timeout_sec: Processing timeout in seconds
            
        Returns:
            Preprocessed image as numpy array or None if failed
        """
        return self.coordinator.preprocess_pdf_page(
            pdf_path, page_num, target_dpi, timeout_sec
        )
    
    def preprocess_with_fallback(
        self,
        pdf_path: Union[str, Path],
        page_num: int,
        timeout_sec: Optional[int] = None
    ) -> Optional[np.ndarray]:
        """
        Preprocess with DPI fallback on timeout.
        
        Maintains exact same API as original implementation.
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number (0-indexed)
            timeout_sec: Processing timeout in seconds
            
        Returns:
            Preprocessed image or None if both attempts fail
        """
        return self.coordinator.preprocess_with_fallback(
            pdf_path, page_num, timeout_sec
        )
    
    # Additional methods that expose new functionality
    def batch_preprocess(
        self,
        pdf_path: Union[str, Path],
        page_numbers: list,
        timeout_per_page: Optional[int] = None
    ) -> dict:
        """
        Preprocess multiple pages in batch (new functionality).
        
        Args:
            pdf_path: Path to PDF file
            page_numbers: List of page numbers to process (0-indexed)
            timeout_per_page: Timeout per individual page
            
        Returns:
            Batch processing results
        """
        return self.coordinator.batch_preprocess_pages(
            pdf_path, page_numbers, timeout_per_page
        )
    
    def validate_pdf(self, pdf_path: Union[str, Path]) -> dict:
        """
        Validate PDF for preprocessing (new functionality).
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Validation results
        """
        return self.coordinator.validate_pdf_for_preprocessing(pdf_path)
    
    def get_status(self) -> dict:
        """
        Get preprocessing system status (new functionality).
        
        Returns:
            System status information
        """
        return self.coordinator.get_preprocessing_status()


# Global preprocessor instance for backward compatibility
_preprocessor_instance = None

def get_preprocessor() -> ImagePreprocessorRefactored:
    """
    Get singleton preprocessor instance.
    
    Maintains exact same API as original implementation.
    """
    global _preprocessor_instance
    if _preprocessor_instance is None:
        _preprocessor_instance = ImagePreprocessorRefactored()
    return _preprocessor_instance


# Convenience functions for backward compatibility
def preprocess_pdf_page(pdf_path: Union[str, Path], page_num: int, **kwargs) -> Optional[np.ndarray]:
    """
    Convenience function for preprocessing a single PDF page.
    
    Maintains exact same API as original implementation.
    """
    return get_preprocessor().preprocess_pdf_page(pdf_path, page_num, **kwargs)


def preprocess_with_fallback(pdf_path: Union[str, Path], page_num: int, **kwargs) -> Optional[np.ndarray]:
    """
    Convenience function for preprocessing with DPI fallback.
    
    Maintains exact same API as original implementation.
    """
    return get_preprocessor().preprocess_with_fallback(pdf_path, page_num, **kwargs)


# Export main functions - same as original
__all__ = [
    'ImagePreprocessorRefactored',
    'get_preprocessor', 
    'preprocess_pdf_page',
    'preprocess_with_fallback'
]

# Alias for backward compatibility
ImagePreprocessor = ImagePreprocessorRefactored






