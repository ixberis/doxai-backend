# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_ocr_engine.py

Core OCR processing engine for PDF pages and images.
Single responsibility: OCR execution from different input sources.

Author: Ixchel Beristáin Mendoza
Date: 28/09/2025 - Refactored from pdf_page_ocr_processor.py
"""

import logging
import tempfile
import os
from pathlib import Path
from typing import Optional, Dict, Any, Union

logger = logging.getLogger(__name__)

# Check dependencies
try:
    # TODO: Implementar módulo RAG completo
    # from app.modules.rag.utils.unstructured_parser_service import parse_with_unstructured
    # from app.modules.rag.converters.pdf_common import elements_to_outputs
    HAS_PARSER_DEPS = False  # Temporalmente False hasta implementar RAG
except ImportError as e:
    logger.error(f"❌ Missing parser dependencies: {e}")
    HAS_PARSER_DEPS = False

try:
    import numpy as np
    from PIL import Image
    HAS_IMAGING = True
except ImportError:
    logger.warning("⚠️ Imaging libraries not available for image OCR")
    HAS_IMAGING = False


class PDFOCREngine:
    """
    Core OCR processing engine for PDF pages and preprocessed images.
    Single responsibility: OCR execution and result processing.
    """
    
    def __init__(self):
        """Initialize OCR engine with dependency checks."""
        if not HAS_PARSER_DEPS:
            raise ImportError("Required parser dependencies not available for PDFOCREngine")
    
    def ocr_from_pdf_page(
        self, 
        pdf_path: Union[str, Path], 
        page_num: int, 
        strategy: str = "hi_res",
        timeout_sec: Optional[int] = None,
        infer_tables: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Process OCR directly from PDF page.
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number (0-indexed)
            strategy: OCR strategy ("fast" or "hi_res")
            timeout_sec: Processing timeout in seconds
            infer_tables: Whether to detect and extract tables
            
        Returns:
            OCR results dictionary with text, tables, forms or None if failed
        """
        page_display_num = page_num + 1  # Convert to 1-indexed for display
        
        try:
            logger.debug(f"🔄 [PAGE {page_display_num}] Starting PDF OCR with {strategy} strategy")
            
            # Use unstructured with page-specific parameters
            elements = parse_with_unstructured(
                str(pdf_path),
                strategy=strategy,
                pages=[page_display_num],  # Convert to 1-indexed for unstructured
                infer_tables=infer_tables,
                timeout_sec=timeout_sec
            )
            
            if not elements:
                logger.warning(f"⚠️ [PAGE {page_display_num}] No elements extracted from PDF")
                return None
            
            # Convert elements to structured output
            result = elements_to_outputs(elements)
            
            if result:
                text_length = len(result.get("text", ""))
                tables_count = len(result.get("tables", []))
                logger.debug(f"✅ [PAGE {page_display_num}] PDF OCR completed: "
                           f"{text_length} chars, {tables_count} tables")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ [PAGE {page_display_num}] PDF OCR failed: {e}")
            return None
    
    def ocr_from_image_array(
        self, 
        image: 'np.ndarray', 
        page_num: int,
        strategy: str = "hi_res",
        infer_tables: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Process OCR from preprocessed image array.
        
        Args:
            image: Preprocessed image as numpy array
            page_num: Page number for logging (1-indexed)
            strategy: OCR strategy ("fast" or "hi_res")
            infer_tables: Whether to detect and extract tables
            
        Returns:
            OCR results dictionary or None if failed
        """
        if not HAS_IMAGING:
            logger.error(f"❌ [PAGE {page_num}] Imaging libraries not available for image OCR")
            return None
        
        temp_path = None
        try:
            logger.debug(f"🔄 [PAGE {page_num}] Starting image OCR with {strategy} strategy")
            
            # Save image to temporary file for OCR processing
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                temp_path = temp_file.name
                
                # Convert numpy array to PIL Image and save
                pil_image = Image.fromarray(image)
                pil_image.save(temp_path)
            
            # Process with unstructured
            elements = parse_with_unstructured(
                temp_path,
                strategy=strategy,
                infer_tables=infer_tables
            )
            
            if not elements:
                logger.warning(f"⚠️ [PAGE {page_num}] No elements extracted from image")
                return None
                
            # Convert elements to structured output
            result = elements_to_outputs(elements)
            
            if result:
                text_length = len(result.get("text", ""))
                tables_count = len(result.get("tables", []))
                logger.debug(f"✅ [PAGE {page_num}] Image OCR completed: "
                           f"{text_length} chars, {tables_count} tables")
            
            return result
                
        except Exception as e:
            logger.error(f"❌ [PAGE {page_num}] Image OCR failed: {e}")
            return None
            
        finally:
            # Clean up temporary file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception as cleanup_error:
                    logger.warning(f"⚠️ Failed to cleanup temp file {temp_path}: {cleanup_error}")
    
    def ocr_from_image_file(
        self,
        image_path: Union[str, Path],
        page_num: int,
        strategy: str = "hi_res", 
        infer_tables: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Process OCR from image file.
        
        Args:
            image_path: Path to image file
            page_num: Page number for logging (1-indexed)
            strategy: OCR strategy ("fast" or "hi_res")
            infer_tables: Whether to detect and extract tables
            
        Returns:
            OCR results dictionary or None if failed
        """
        try:
            if not Path(image_path).exists():
                logger.error(f"❌ [PAGE {page_num}] Image file does not exist: {image_path}")
                return None
                
            logger.debug(f"🔄 [PAGE {page_num}] Starting file OCR with {strategy} strategy")
            
            # Process with unstructured directly
            elements = parse_with_unstructured(
                str(image_path),
                strategy=strategy,
                infer_tables=infer_tables
            )
            
            if not elements:
                logger.warning(f"⚠️ [PAGE {page_num}] No elements extracted from image file")
                return None
                
            # Convert elements to structured output
            result = elements_to_outputs(elements)
            
            if result:
                text_length = len(result.get("text", ""))
                tables_count = len(result.get("tables", []))
                logger.debug(f"✅ [PAGE {page_num}] File OCR completed: "
                           f"{text_length} chars, {tables_count} tables")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ [PAGE {page_num}] File OCR failed: {e}")
            return None
    
    def validate_ocr_result(self, result: Dict[str, Any], page_num: int) -> bool:
        """
        Validate OCR result quality and completeness.
        
        Args:
            result: OCR result dictionary
            page_num: Page number for logging
            
        Returns:
            True if result passes basic validation
        """
        if not result:
            logger.warning(f"⚠️ [PAGE {page_num}] Empty OCR result")
            return False
        
        # Check for required keys
        required_keys = ["text", "tables", "forms"]
        missing_keys = [key for key in required_keys if key not in result]
        
        if missing_keys:
            logger.warning(f"⚠️ [PAGE {page_num}] OCR result missing keys: {missing_keys}")
            return False
        
        # Check text content
        text_content = result.get("text", "").strip()
        if not text_content:
            logger.warning(f"⚠️ [PAGE {page_num}] OCR result contains no text content")
            # Still return True as some pages might legitimately have no text (images only)
        
        # Basic length validation
        if len(text_content) > 100000:  # > 100KB of text seems excessive for one page
            logger.warning(f"⚠️ [PAGE {page_num}] OCR result unusually large: {len(text_content)} chars")
        
        logger.debug(f"✅ [PAGE {page_num}] OCR result validation passed")
        return True
    
    def get_ocr_statistics(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate statistics for OCR result.
        
        Args:
            result: OCR result dictionary
            
        Returns:
            Dictionary with OCR statistics
        """
        if not result:
            return {"error": "No result provided"}
        
        try:
            text_content = result.get("text", "")
            tables = result.get("tables", [])
            forms = result.get("forms", [])
            
            # Basic text statistics
            text_stats = {
                "character_count": len(text_content),
                "word_count": len(text_content.split()) if text_content else 0,
                "line_count": text_content.count('\n') + 1 if text_content else 0,
                "paragraph_count": len([p for p in text_content.split('\n\n') if p.strip()]) if text_content else 0
            }
            
            # Table statistics
            table_stats = {
                "table_count": len(tables),
                "total_cells": sum(len(table.get("rows", [])) * len(table.get("rows", [[]])[0]) 
                                 for table in tables if table.get("rows"))
            }
            
            # Form statistics
            form_stats = {
                "form_count": len(forms),
                "total_fields": sum(len(form.get("fields", [])) for form in forms)
            }
            
            return {
                "text": text_stats,
                "tables": table_stats, 
                "forms": form_stats,
                "overall": {
                    "has_content": bool(text_content or tables or forms),
                    "content_types": [
                        "text" if text_content else None,
                        "tables" if tables else None,
                        "forms" if forms else None
                    ]
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to generate OCR statistics: {e}")
            return {"error": str(e)}






