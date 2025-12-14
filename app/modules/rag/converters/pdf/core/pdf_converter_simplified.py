# -*- coding: utf-8 -*-
"""
Simplified PDF Converter - Clean wrapper for the refactored orchestrator.
"""

from typing import Optional, Dict, Union, List
from pathlib import Path
import logging

from .pdf_adaptive_controller import convert_pdf_adaptive
from .pdf_conversion_config import get_settings

logger = logging.getLogger(__name__)

def convert_pdf_to_text(
    file_path: str, 
    strict_table_mode: bool = False, 
    job_id: str = None
) -> Optional[Dict[str, Union[str, List]]]:
    """
    Clean PDF conversion using the adaptive converter.
    
    Args:
        file_path: PDF file path
        strict_table_mode: Enable high-res for table pages only
        job_id: Job ID for cancellation tracking
        
    Returns:
        Dict with 'text', 'tables', 'forms', 'md_size_bytes', 'no_text_extracted'
    """
    try:
        # Convert to Path object
        pdf_path = Path(file_path) if isinstance(file_path, str) else file_path
        
        # Use the main adaptive converter function
        result = convert_pdf_adaptive(
            pdf_path=pdf_path,
            job_id=job_id,
            strict_table_mode=strict_table_mode
        )
        
        if not result:
            logger.error(f"❌ Conversion failed for {pdf_path.name}")
            return _create_empty_result()
        
        # Extract text and validate
        text = result.get('text', '').strip()
        
        # Calculate size and set flags
        md_bytes = text.encode('utf-8') if text else b''
        result['md_size_bytes'] = len(md_bytes)
        result['no_text_extracted'] = len(text) < 50  # Minimal text threshold
        
        # Ensure all expected keys exist
        result.setdefault('text', text)
        result.setdefault('tables', [])
        result.setdefault('forms', [])
        
        logger.info(f"✅ PDF converted: {len(text)} chars, {len(result.get('tables', []))} tables")
        return result
        
    except Exception as e:
        logger.error(f"❌ Error converting PDF {file_path}: {e}")
        return _create_empty_result()


def _create_empty_result() -> Dict[str, Union[str, List, bool, int]]:
    """Creates an empty result structure for failed conversions."""
    return {
        'text': '',
        'tables': [],
        'forms': [],
        'md_size_bytes': 0,
        'no_text_extracted': True
    }


def get_conversion_result_template() -> Dict[str, Union[str, List, bool, int]]:
    """Returns template for PDF conversion results."""
    return _create_empty_result()


def validate_conversion_result(result: Dict) -> bool:
    """Validates that a conversion result has the expected structure."""
    required_keys = {'text', 'tables', 'forms', 'md_size_bytes', 'no_text_extracted'}
    return all(key in result for key in required_keys)


# Backward compatibility functions for Phase 5 integration
def convert_with_adaptive_processing(
    pdf_path: Path, 
    job_id: str = None
) -> Optional[Dict[str, Union[str, List]]]:
    """
    Backward compatibility function for Phase 5 processing.
    Direct wrapper around convert_pdf_adaptive for legacy compatibility.
    """
    try:
        logger.info("🎯 Starting adaptive PDF processing (Phase 5 compatibility)")
        
        result = convert_pdf_adaptive(
            pdf_path=pdf_path,
            job_id=job_id
        )
        
        if result:
            logger.info("✅ Adaptive processing completed successfully")
            return result
        else:
            logger.warning("⚠️ Adaptive processing returned no results")
            return None
            
    except Exception as e:
        logger.error(f"❌ Adaptive processing error: {e}")
        return None


# Alias for backward compatibility
convert_with_phase5 = convert_with_adaptive_processing






