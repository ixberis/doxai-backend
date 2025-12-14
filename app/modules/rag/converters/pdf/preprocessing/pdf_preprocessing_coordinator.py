# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_preprocessing_coordinator.py

Main coordinator for PDF image preprocessing pipeline.
Single responsibility: orchestrating the complete preprocessing workflow.

Author: Ixchel Beristáin Mendoza
Date: 28/09/2025 - Refactored from pdf_image_preprocessing.py
"""

import logging
from pathlib import Path
from typing import Optional, Union
import time
import numpy as np

from .pdf_page_renderer import PDFPageRenderer
from .pdf_image_enhancement import PDFImageEnhancer
from .pdf_preprocessing_config import PDFPreprocessingConfigManager
from app.shared.config import settings

logger = logging.getLogger(__name__)


class PDFPreprocessingCoordinator:
    """
    Coordinates the complete PDF image preprocessing pipeline.
    Single responsibility: orchestrating rendering and enhancement operations.
    """
    
    def __init__(self):
        """Initialize coordinator with specialized components."""
        self.renderer = PDFPageRenderer()
        self.enhancer = PDFImageEnhancer()
        self.config_manager = PDFPreprocessingConfigManager()
    
    def preprocess_pdf_page(
        self, 
        pdf_path: Union[str, Path], 
        page_num: int,
        target_dpi: Optional[int] = None,
        timeout_sec: Optional[int] = None
    ) -> Optional[np.ndarray]:
        """
        Complete preprocessing pipeline for a single PDF page.
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number (0-indexed)
            target_dpi: Override DPI (uses config default if None)
            timeout_sec: Processing timeout in seconds
            
        Returns:
            Preprocessed image as numpy array or None if failed
        """
        start_time = time.time()
        config = self.config_manager.get_config()
        
        effective_dpi = target_dpi or config.dpi
        effective_timeout = timeout_sec or config.timeout_per_page
        
        if settings.logging.ocr_per_page:
            logger.info(f"🖼️ [PAGE {page_num + 1}] Starting preprocessing pipeline at {effective_dpi} DPI")
        
        try:
            # Step 1: Render PDF page to image
            image_data = self.renderer.render_pdf_page(
                pdf_path, page_num, effective_dpi, effective_timeout
            )
            
            if image_data is None:
                logger.error(f"❌ [PAGE {page_num + 1}] Failed to render page")
                return None
            
            # Check timeout after rendering
            if effective_timeout and (time.time() - start_time) > effective_timeout:
                logger.warning(f"⏰ [PAGE {page_num + 1}] Timeout during rendering")
                return None
            
            # Step 2: Apply image enhancement pipeline
            enhancement_settings = self.config_manager.get_enhancement_settings()
            
            enhanced_image = self.enhancer.enhance_image_pipeline(
                image=image_data,
                grayscale=enhancement_settings['grayscale_enabled'],
                deskew=enhancement_settings['deskew_enabled'],
                binarize=enhancement_settings['binarize_enabled'],
                noise_reduction=enhancement_settings['noise_reduction_enabled']
            )
            
            # Final timeout check
            processing_time = time.time() - start_time
            if effective_timeout and processing_time > effective_timeout:
                logger.warning(f"⏰ [PAGE {page_num + 1}] Timeout during enhancement")
                return None
            
            if settings.logging.ocr_timing_details:
                logger.info(f"✅ [PAGE {page_num + 1}] Preprocessing completed in {processing_time:.2f}s")
            
            return enhanced_image
            
        except Exception as e:
            logger.error(f"❌ [PAGE {page_num + 1}] Preprocessing pipeline failed: {e}")
            return None
    
    def preprocess_with_fallback(
        self,
        pdf_path: Union[str, Path],
        page_num: int,
        timeout_sec: Optional[int] = None
    ) -> Optional[np.ndarray]:
        """
        Preprocess with DPI fallback on timeout or failure.
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number (0-indexed)
            timeout_sec: Processing timeout in seconds
            
        Returns:
            Preprocessed image or None if both attempts fail
        """
        config = self.config_manager.get_config()
        
        # First attempt with configured DPI
        result = self.preprocess_pdf_page(
            pdf_path, page_num, config.dpi, timeout_sec
        )
        
        if result is not None:
            return result
        
        # Fallback attempt with lower DPI
        if config.dpi_fallback < config.dpi:
            if settings.logging.ocr_strategy_switch:
                logger.warning(f"🔄 [PAGE {page_num + 1}] Falling back to {config.dpi_fallback} DPI")
            
            return self.preprocess_pdf_page(
                pdf_path, page_num, config.dpi_fallback, timeout_sec
            )
        
        logger.error(f"❌ [PAGE {page_num + 1}] All preprocessing attempts failed")
        return None
    
    def batch_preprocess_pages(
        self,
        pdf_path: Union[str, Path],
        page_numbers: list,
        timeout_per_page: Optional[int] = None
    ) -> dict:
        """
        Preprocess multiple pages in batch.
        
        Args:
            pdf_path: Path to PDF file
            page_numbers: List of page numbers to process (0-indexed)
            timeout_per_page: Timeout per individual page
            
        Returns:
            Dictionary with results for each page
        """
        results = {}
        total_pages = len(page_numbers)
        
        logger.info(f"🔄 Starting batch preprocessing: {total_pages} pages from {Path(pdf_path).name}")
        
        for i, page_num in enumerate(page_numbers):
            try:
                result = self.preprocess_with_fallback(
                    pdf_path, page_num, timeout_per_page
                )
                
                results[page_num] = {
                    'success': result is not None,
                    'image': result,
                    'error': None if result is not None else 'Preprocessing failed'
                }
                
                if settings.logging.ocr_per_page:
                    status = "✅ SUCCESS" if result is not None else "❌ FAILED"
                    logger.info(f"📄 [{i+1}/{total_pages}] Page {page_num + 1}: {status}")
                
            except Exception as e:
                logger.error(f"❌ Error preprocessing page {page_num + 1}: {e}")
                results[page_num] = {
                    'success': False,
                    'image': None,
                    'error': str(e)
                }
        
        # Calculate batch statistics
        successful_pages = sum(1 for r in results.values() if r['success'])
        success_rate = (successful_pages / total_pages) * 100 if total_pages > 0 else 0
        
        logger.info(f"📊 Batch preprocessing completed: {successful_pages}/{total_pages} pages "
                   f"({success_rate:.1f}% success rate)")
        
        return {
            'results': results,
            'statistics': {
                'total_pages': total_pages,
                'successful_pages': successful_pages,
                'failed_pages': total_pages - successful_pages,
                'success_rate': success_rate
            }
        }
    
    def validate_pdf_for_preprocessing(self, pdf_path: Union[str, Path]) -> dict:
        """
        Validate PDF file for preprocessing operations.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Validation results dictionary
        """
        try:
            # Check if file exists
            if not Path(pdf_path).exists():
                return {'valid': False, 'error': 'PDF file does not exist'}
            
            # Validate PDF with renderer
            if not self.renderer.validate_pdf_file(pdf_path):
                return {'valid': False, 'error': 'PDF file cannot be opened or is corrupted'}
            
            # Get page count
            page_count = self.renderer.get_pdf_page_count(pdf_path)
            if page_count == 0:
                return {'valid': False, 'error': 'PDF contains no pages'}
            
            # Validate configuration
            if not self.config_manager.validate_config():
                return {'valid': False, 'error': 'Invalid preprocessing configuration'}
            
            return {
                'valid': True,
                'page_count': page_count,
                'config_summary': self.config_manager.get_config_summary()
            }
            
        except Exception as e:
            logger.error(f"❌ PDF validation failed for {pdf_path}: {e}")
            return {'valid': False, 'error': str(e)}
    
    def get_preprocessing_status(self) -> dict:
        """
        Get current preprocessing system status.
        
        Returns:
            Status information dictionary
        """
        config = self.config_manager.get_config()
        
        return {
            'renderer_available': True,  # Always available if class instantiated
            'enhancer_available': True,
            'config_valid': self.config_manager.validate_config(),
            'current_config': {
                'dpi': config.dpi,
                'dpi_fallback': config.dpi_fallback,
                'enhancements_enabled': {
                    'grayscale': config.grayscale_enabled,
                    'deskew': config.deskew_enabled,
                    'binarize': config.binarize_enabled,
                    'noise_reduction': config.noise_reduction_enabled
                }
            }
        }






