# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_parallel_worker.py

Worker functions for PDF parallel processing operations.
Single responsibility: multiprocessing-compatible worker functions.

Author: Ixchel Beristáin Mendoza
Date: 28/09/2025 - Refactored from pdf_parallel_page_processor.py
"""

import logging
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)


def process_single_page_worker(
    pdf_path_str: str,
    page_idx: int,
    strategy: str = "hi_res",
    timeout_sec: Optional[int] = None,
    max_retries: int = 2,
    enable_preprocessing: bool = True
) -> Tuple[int, Optional[Dict[str, Any]]]:
    """
    Worker function for processing a single PDF page in parallel.
    
    This function is designed to be pickle-able for multiprocessing and contains
    all necessary imports to avoid pickling issues.
    
    Args:
        pdf_path_str: PDF file path as string (for pickle compatibility)
        page_idx: Page index (0-indexed)
        strategy: OCR strategy ("fast" or "hi_res")
        timeout_sec: Processing timeout in seconds
        max_retries: Maximum retry attempts
        enable_preprocessing: Whether to enable image preprocessing
        
    Returns:
        Tuple of (page_index, result_dict or None)
    """
    try:
        # Import inside worker to avoid pickling issues
        # TODO: Implementar módulo RAG completo
        # from app.modules.rag.converters.pdf_page_ocr_processor_refactored import get_page_processor
        
        # Create processor instance in worker process
        # processor = get_page_processor()
        
        # Temporalmente retornar None hasta que RAG esté implementado
        logger.warning(f"⚠️ RAG module not implemented - skipping page {page_index}")
        return (page_index, None)
        
        # Process page with retry logic
        if max_retries > 0:
            result = processor.process_page_with_retry(
                pdf_path=pdf_path_str, 
                page_num=page_idx, 
                max_retries=max_retries, 
                strategy=strategy
            )
        else:
            result = processor.process_single_page(
                pdf_path=pdf_path_str,
                page_num=page_idx,
                strategy=strategy,
                timeout_override=timeout_sec
            )
        
        # Log worker completion
        if result:
            text_len = len(result.get("text", ""))
            tables_count = len(result.get("tables", []))
            logger.debug(f"✅ Worker completed page {page_idx + 1}: {text_len} chars, {tables_count} tables")
        else:
            logger.warning(f"⚠️ Worker failed for page {page_idx + 1}")
        
        return (page_idx, result)
        
    except Exception as e:
        logger.error(f"❌ Worker error for page {page_idx + 1}: {e}")
        return (page_idx, None)


def process_batch_worker(
    pdf_path_str: str,
    page_indices: list,
    strategy: str = "hi_res",
    timeout_sec: Optional[int] = None,
    max_retries: int = 2
) -> Tuple[list, Dict[int, Optional[Dict[str, Any]]]]:
    """
    Worker function for processing a batch of PDF pages sequentially within a worker process.
    
    This can be useful for reducing process overhead when processing small batches.
    
    Args:
        pdf_path_str: PDF file path as string
        page_indices: List of page indices to process
        strategy: OCR strategy
        timeout_sec: Processing timeout per page
        max_retries: Maximum retry attempts per page
        
    Returns:
        Tuple of (page_indices, results_dict)
    """
    results = {}
    
    try:
        # Import inside worker
        # TODO: Implementar módulo RAG completo
        # from app.modules.rag.converters.pdf_page_ocr_processor_refactored import get_page_processor
        
        # processor = get_page_processor()
        
        # Temporalmente retornar resultados vacíos hasta que RAG esté implementado
        logger.warning(f"⚠️ RAG module not implemented - skipping batch {page_indices}")
        return (page_indices, {})
        
        for page_idx in page_indices:
            try:
                if max_retries > 0:
                    result = processor.process_page_with_retry(
                        pdf_path=pdf_path_str,
                        page_num=page_idx,
                        max_retries=max_retries,
                        strategy=strategy
                    )
                else:
                    result = processor.process_single_page(
                        pdf_path=pdf_path_str,
                        page_num=page_idx,
                        strategy=strategy,
                        timeout_override=timeout_sec
                    )
                
                results[page_idx] = result
                
            except Exception as e:
                logger.error(f"❌ Batch worker error for page {page_idx + 1}: {e}")
                results[page_idx] = None
        
        logger.debug(f"✅ Batch worker completed {len(page_indices)} pages")
        return (page_indices, results)
        
    except Exception as e:
        logger.error(f"❌ Batch worker failed: {e}")
        return (page_indices, {idx: None for idx in page_indices})


def validate_worker_environment() -> Dict[str, bool]:
    """
    Validate that the worker environment has all necessary dependencies.
    
    This function can be called to check if the multiprocessing workers
    will have access to required modules.
    
    Returns:
        Dictionary with availability status of required components
    """
    validation_result = {
        "page_processor_available": False,
        "settings_available": False,
        "logging_available": True  # logging is always available
    }
    
    try:
        # TODO: Implementar módulo RAG completo
        # from app.modules.rag.converters.pdf_page_ocr_processor_refactored import get_page_processor
        # processor = get_page_processor()
        validation_result["page_processor_available"] = False  # Temporalmente False
    except Exception as e:
        logger.warning(f"Page processor not available in worker: {e}")
    
    try:
        from app.shared.config import settings
        validation_result["settings_available"] = True
    except Exception as e:
        logger.warning(f"Settings not available in worker: {e}")
    
    return validation_result


def worker_health_check(worker_id: int = 0) -> Dict[str, Any]:
    """
    Perform a health check in a worker process.
    
    Args:
        worker_id: Worker identifier for tracking
        
    Returns:
        Dictionary with worker health information
    """
    import os
    import time
    import multiprocessing as mp
    
    start_time = time.time()
    
    try:
        # Basic environment check
        validation = validate_worker_environment()
        
        # Process information
        process_info = {
            "worker_id": worker_id,
            "process_id": os.getpid(),
            "process_name": mp.current_process().name,
            "cpu_count": mp.cpu_count()
        }
        
        # Simple performance test
        test_start = time.time()
        # Perform simple computation
        _ = sum(i * i for i in range(1000))
        computation_time = time.time() - test_start
        
        total_time = time.time() - start_time
        
        return {
            "healthy": True,
            "validation": validation,
            "process_info": process_info,
            "performance": {
                "health_check_time": total_time,
                "computation_time": computation_time
            },
            "timestamp": time.time()
        }
        
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e),
            "worker_id": worker_id,
            "timestamp": time.time()
        }


# === Backward Compatibility Alias ===
# Some tests patch "process_single_page" in this module.
# Create an alias to maintain backward compatibility.
process_single_page = process_single_page_worker







