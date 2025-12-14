# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_ocr_retry_handler.py

Retry logic and error recovery for PDF OCR operations.
Single responsibility: managing retry attempts and error recovery strategies.

Author: Ixchel Beristáin Mendoza
Date: 28/09/2025 - Refactored from pdf_page_ocr_processor.py
"""

import time
import logging
from typing import Optional, Dict, Any, Callable, List, Union
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)


class RetryStrategy(Enum):
    """Enumeration of available retry strategies."""
    IMMEDIATE = "immediate"
    LINEAR_BACKOFF = "linear_backoff"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    ADAPTIVE = "adaptive"


class PDFOCRRetryHandler:
    """
    Handles retry logic and error recovery for PDF OCR operations.
    Single responsibility: retry attempts and recovery strategies.
    """
    
    def __init__(
        self,
        max_retries: int = 2,
        retry_strategy: RetryStrategy = RetryStrategy.LINEAR_BACKOFF,
        base_delay: float = 0.5
    ):
        """
        Initialize retry handler.
        
        Args:
            max_retries: Maximum number of retry attempts
            retry_strategy: Strategy for retry delays
            base_delay: Base delay in seconds for retry strategies
        """
        self.max_retries = max_retries
        self.retry_strategy = retry_strategy
        self.base_delay = base_delay
        
        # Track retry statistics
        self.retry_counts = {}  # page_num -> retry_count
        self.failure_reasons = {}  # page_num -> list of failure reasons
        
        logger.debug(f"🔄 Retry handler initialized: max_retries={max_retries}, "
                    f"strategy={retry_strategy.value}")
    
    def execute_with_retry(
        self,
        operation_func: Callable,
        page_num: int,
        operation_name: str = "OCR",
        timeout_reduction_factor: float = 0.8,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Execute operation with retry logic.
        
        Args:
            operation_func: Function to execute
            page_num: Page number for tracking and logging
            operation_name: Name of operation for logging
            timeout_reduction_factor: Factor to reduce timeout on retries (0.8 = 20% reduction)
            **kwargs: Arguments to pass to operation_func
            
        Returns:
            Operation result or None if all retries exhausted
        """
        page_display_num = page_num if page_num > 0 else page_num + 1
        original_timeout = kwargs.get('timeout_override')
        
        # Initialize tracking for this page
        if page_num not in self.retry_counts:
            self.retry_counts[page_num] = 0
            self.failure_reasons[page_num] = []
        
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    # Apply retry delay
                    delay = self._calculate_retry_delay(attempt)
                    
                    logger.info(f"🔄 [PAGE {page_display_num}] Retry attempt {attempt} "
                               f"after {delay:.1f}s delay")
                    
                    time.sleep(delay)
                    
                    # Reduce timeout for retries to avoid getting stuck
                    if original_timeout:
                        reduced_timeout = max(30, int(original_timeout * (timeout_reduction_factor ** attempt)))
                        kwargs['timeout_override'] = reduced_timeout
                        
                        logger.debug(f"⏱️ [PAGE {page_display_num}] Reduced timeout to {reduced_timeout}s "
                                   f"for retry {attempt}")
                
                # Execute operation
                result = operation_func(**kwargs)
                
                # Check if result is valid
                if self._is_valid_result(result, page_display_num, operation_name):
                    if attempt > 0:
                        logger.info(f"✅ [PAGE {page_display_num}] {operation_name} succeeded on retry {attempt}")
                        self.retry_counts[page_num] = attempt
                    
                    return result
                else:
                    # Invalid result - count as failure
                    failure_reason = f"invalid_result_attempt_{attempt}"
                    self.failure_reasons[page_num].append(failure_reason)
                    
                    if attempt < self.max_retries:
                        logger.warning(f"⚠️ [PAGE {page_display_num}] {operation_name} returned invalid result, retrying...")
                    continue
                
            except Exception as e:
                failure_reason = f"{type(e).__name__}_attempt_{attempt}: {str(e)}"
                self.failure_reasons[page_num].append(failure_reason)
                
                logger.warning(f"⚠️ [PAGE {page_display_num}] {operation_name} attempt {attempt} failed: {e}")
                
                # If this is the last attempt, log final failure
                if attempt >= self.max_retries:
                    break
                
                # Continue to next attempt
                continue
        
        # All retries exhausted
        self.retry_counts[page_num] = self.max_retries + 1  # Mark as fully failed
        
        logger.error(f"❌ [PAGE {page_display_num}] {operation_name} failed after {self.max_retries + 1} attempts")
        logger.error(f"❌ [PAGE {page_display_num}] Failure reasons: {self.failure_reasons[page_num]}")
        
        return None
    
    def _calculate_retry_delay(self, attempt: int) -> float:
        """
        Calculate delay before retry based on strategy.
        
        Args:
            attempt: Current attempt number (1-indexed)
            
        Returns:
            Delay in seconds
        """
        if self.retry_strategy == RetryStrategy.IMMEDIATE:
            return 0.0
        
        elif self.retry_strategy == RetryStrategy.LINEAR_BACKOFF:
            return self.base_delay * attempt
        
        elif self.retry_strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            return self.base_delay * (2 ** (attempt - 1))
        
        elif self.retry_strategy == RetryStrategy.ADAPTIVE:
            # Adaptive strategy considers previous failures
            avg_failures = sum(len(reasons) for reasons in self.failure_reasons.values())
            if avg_failures > 0:
                avg_failures /= len(self.failure_reasons)
            
            # Increase delay based on overall failure rate
            adaptive_multiplier = 1.0 + (avg_failures * 0.5)
            return self.base_delay * attempt * adaptive_multiplier
        
        else:
            return self.base_delay
    
    def _is_valid_result(self, result: Any, page_num: int, operation_name: str) -> bool:
        """
        Validate if operation result is acceptable.
        
        Args:
            result: Operation result to validate
            page_num: Page number for logging
            operation_name: Operation name for logging
            
        Returns:
            True if result is valid and acceptable
        """
        if result is None:
            logger.debug(f"❌ [PAGE {page_num}] {operation_name} result is None")
            return False
        
        # For OCR results, check structure
        if isinstance(result, dict):
            required_keys = ["text", "tables", "forms"]
            if not all(key in result for key in required_keys):
                missing = [key for key in required_keys if key not in result]
                logger.debug(f"❌ [PAGE {page_num}] {operation_name} result missing keys: {missing}")
                return False
            
            # Check if result has any content
            text_content = result.get("text", "").strip()
            tables = result.get("tables", [])
            forms = result.get("forms", [])
            
            if not text_content and not tables and not forms:
                logger.debug(f"❌ [PAGE {page_num}] {operation_name} result has no content")
                # This might be valid for some pages (e.g., blank pages), so we'll accept it
                # but log it as a warning
                logger.warning(f"⚠️ [PAGE {page_num}] {operation_name} extracted no content (might be blank page)")
                return True
        
        logger.debug(f"✅ [PAGE {page_num}] {operation_name} result validation passed")
        return True
    
    def get_retry_statistics(self) -> Dict[str, Any]:
        """
        Get retry statistics for analysis.
        
        Returns:
            Dictionary with retry statistics
        """
        if not self.retry_counts:
            return {"no_operations": True}
        
        total_operations = len(self.retry_counts)
        successful_operations = sum(1 for count in self.retry_counts.values() if count <= self.max_retries)
        failed_operations = total_operations - successful_operations
        
        retry_distribution = {}
        for count in self.retry_counts.values():
            if count <= self.max_retries:
                retry_distribution[f"attempts_{count}"] = retry_distribution.get(f"attempts_{count}", 0) + 1
            else:
                retry_distribution["failed"] = retry_distribution.get("failed", 0) + 1
        
        # Most common failure reasons
        all_failures = []
        for reasons in self.failure_reasons.values():
            all_failures.extend(reasons)
        
        failure_types = {}
        for reason in all_failures:
            failure_type = reason.split('_attempt_')[0] if '_attempt_' in reason else reason
            failure_types[failure_type] = failure_types.get(failure_type, 0) + 1
        
        return {
            "total_operations": total_operations,
            "successful_operations": successful_operations,
            "failed_operations": failed_operations,
            "success_rate": (successful_operations / total_operations) * 100 if total_operations > 0 else 0,
            "retry_distribution": retry_distribution,
            "common_failure_types": dict(sorted(failure_types.items(), key=lambda x: x[1], reverse=True)[:5])
        }
    
    def reset_statistics(self):
        """Reset retry statistics."""
        self.retry_counts.clear()
        self.failure_reasons.clear()
        logger.debug("🔄 Retry statistics reset")
    
    def should_skip_retries(self, page_num: int) -> bool:
        """
        Determine if retries should be skipped for a page based on history.
        
        Args:
            page_num: Page number to check
            
        Returns:
            True if retries should be skipped for this page
        """
        # Skip retries if page consistently fails
        if page_num in self.failure_reasons:
            failure_count = len(self.failure_reasons[page_num])
            
            # If page has failed many times across different runs, skip retries
            if failure_count > self.max_retries * 2:
                logger.info(f"⏭️ [PAGE {page_num + 1}] Skipping retries due to consistent failures "
                           f"({failure_count} previous failures)")
                return True
        
        return False
    
    def get_failure_summary(self, page_num: int) -> str:
        """
        Get human-readable failure summary for a page.
        
        Args:
            page_num: Page number
            
        Returns:
            Formatted failure summary
        """
        if page_num not in self.failure_reasons:
            return "No failures recorded"
        
        failures = self.failure_reasons[page_num]
        retry_count = self.retry_counts.get(page_num, 0)
        
        return (
            f"Page {page_num + 1} Failure Summary:\n"
            f"  Retry attempts: {min(retry_count, self.max_retries)}/{self.max_retries}\n"
            f"  Total failures: {len(failures)}\n"
            f"  Failure types: {list(set(f.split('_attempt_')[0] for f in failures))}"
        )






