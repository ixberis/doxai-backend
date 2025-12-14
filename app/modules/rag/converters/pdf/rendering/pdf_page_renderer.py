# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_page_renderer.py

PDF page rendering operations for image preprocessing.
Single responsibility: converting PDF pages to image arrays at specified DPI.

Author: Ixchel Beristáin Mendoza
Date: 28/09/2025 - Refactored from pdf_image_preprocessing.py
"""

import io
import logging
from pathlib import Path
from typing import Optional, Union
import time

import numpy as np
from PIL import Image
from app.shared.config import settings

logger = logging.getLogger(__name__)

# Check PyMuPDF availability
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    logger.warning("⚠️ PyMuPDF not available. PDF rendering will be limited.")
    HAS_PYMUPDF = False


class PDFPageRenderer:
    """
    Renders PDF pages to image arrays at specified DPI.
    Single responsibility: PDF to image conversion.
    """
    
    def __init__(self):
        """Initialize renderer with configuration."""
        self.default_dpi = getattr(settings.ocr, 'dpi', 300)
    
    def render_pdf_page(
        self, 
        pdf_path: Union[str, Path], 
        page_num: int, 
        dpi: Optional[int] = None,
        timeout_sec: Optional[int] = None
    ) -> Optional[np.ndarray]:
        """
        Render PDF page to numpy array at specified DPI.
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number (0-indexed)
            dpi: Target DPI resolution (uses default if None)
            timeout_sec: Rendering timeout in seconds
            
        Returns:
            Image as numpy array or None if failed
        """
        if not HAS_PYMUPDF:
            logger.error("❌ PyMuPDF not available for PDF rendering")
            return None
        
        effective_dpi = dpi or self.default_dpi
        start_time = time.time()
        
        if settings.logging.ocr_per_page:
            logger.info(f"📄 [PAGE {page_num + 1}] Rendering at {effective_dpi} DPI")
        
        try:
            doc = fitz.open(str(pdf_path))
            
            # Validate page number
            if page_num >= len(doc):
                logger.error(f"❌ Page {page_num + 1} out of range (max: {len(doc)})")
                doc.close()
                return None
            
            # Check timeout before processing
            if timeout_sec and (time.time() - start_time) > timeout_sec:
                logger.warning(f"⏰ [PAGE {page_num + 1}] Timeout before rendering")
                doc.close()
                return None
            
            page = doc.load_page(page_num)
            
            # Calculate zoom factor for target DPI (PyMuPDF default is 72 DPI)
            zoom = effective_dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            
            # Render page to pixmap
            pix = page.get_pixmap(matrix=mat)
            
            # Convert to PIL Image then to numpy array
            img_data = pix.tobytes("ppm")
            pil_image = Image.open(io.BytesIO(img_data))
            image_array = np.array(pil_image)
            
            doc.close()
            
            render_time = time.time() - start_time
            
            if settings.logging.ocr_per_page:
                logger.info(f"✅ [PAGE {page_num + 1}] Rendered in {render_time:.2f}s, size: {image_array.shape}")
            
            return image_array
            
        except Exception as e:
            logger.error(f"❌ Failed to render PDF page {page_num + 1}: {e}")
            return None
    
    def render_with_fallback_dpi(
        self,
        pdf_path: Union[str, Path], 
        page_num: int,
        primary_dpi: int,
        fallback_dpi: int,
        timeout_sec: Optional[int] = None
    ) -> Optional[np.ndarray]:
        """
        Render PDF page with DPI fallback on failure or timeout.
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number (0-indexed)
            primary_dpi: Primary DPI to try first
            fallback_dpi: Fallback DPI if primary fails
            timeout_sec: Timeout for each rendering attempt
            
        Returns:
            Rendered image array or None if both attempts fail
        """
        # First attempt with primary DPI
        result = self.render_pdf_page(pdf_path, page_num, primary_dpi, timeout_sec)
        
        if result is not None:
            return result
        
        # Fallback attempt with lower DPI
        if fallback_dpi < primary_dpi:
            if settings.logging.ocr_strategy_switch:
                logger.warning(f"🔄 [PAGE {page_num + 1}] Falling back to {fallback_dpi} DPI")
            
            return self.render_pdf_page(pdf_path, page_num, fallback_dpi, timeout_sec)
        
        logger.error(f"❌ [PAGE {page_num + 1}] All rendering attempts failed")
        return None
    
    def get_pdf_page_count(self, pdf_path: Union[str, Path]) -> int:
        """
        Get total number of pages in PDF.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Number of pages or 0 if failed
        """
        if not HAS_PYMUPDF:
            logger.error("❌ PyMuPDF not available for PDF info")
            return 0
        
        try:
            doc = fitz.open(str(pdf_path))
            page_count = len(doc)
            doc.close()
            return page_count
        except Exception as e:
            logger.error(f"❌ Failed to get page count for {pdf_path}: {e}")
            return 0
    
    def validate_pdf_file(self, pdf_path: Union[str, Path]) -> bool:
        """
        Validate if PDF file can be opened and processed.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            True if PDF is valid and processable
        """
        if not HAS_PYMUPDF:
            return False
        
        try:
            doc = fitz.open(str(pdf_path))
            is_valid = len(doc) > 0
            doc.close()
            return is_valid
        except Exception as e:
            logger.error(f"❌ PDF validation failed for {pdf_path}: {e}")
            return False






