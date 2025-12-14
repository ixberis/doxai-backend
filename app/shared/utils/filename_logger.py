# -*- coding: utf-8 -*-
"""
backend/app/utils/filename_logger.py

Specialized logging utilities for filename sanitization operations.
Provides detailed logging and metrics for character problematic detection.

Autor: Ixchel Beristain
Creado: 26/09/2025
"""

import logging
import time
from typing import Dict, List, Optional, Any
from collections import defaultdict, Counter
from dataclasses import dataclass, asdict
from datetime import datetime

from .filename_config import FilenameSanitizationRules


@dataclass
class SanitizationResult:
    """Detailed result of filename sanitization operation"""
    original: str
    sanitized: str
    changed: bool
    processing_time_ms: float
    problematic_chars: Dict[str, list]
    transformations: List[str]
    warnings: List[str]
    timestamp: datetime


class FilenameSanitizationLogger:
    """Specialized logger for filename sanitization operations"""
    
    def __init__(self, logger_name: str = "filename_sanitization"):
        self.logger = logging.getLogger(logger_name)
        self.metrics = {
            'total_processed': 0,
            'total_changed': 0,
            'processing_time_total': 0.0,
            'character_frequency': Counter(),
            'transformation_frequency': Counter(),
            'error_patterns': defaultdict(int)
        }
    
    def log_sanitization(
        self, 
        original: str, 
        sanitized: str, 
        processing_time_ms: float,
        user_email: Optional[str] = None,
        project_context: Optional[str] = None
    ) -> SanitizationResult:
        """
        Log a filename sanitization operation with full details.
        
        Args:
            original: Original filename
            sanitized: Sanitized filename
            processing_time_ms: Processing time in milliseconds
            user_email: User email for context
            project_context: Project context information
            
        Returns:
            SanitizationResult with full operation details
        """
        # Analyze problematic characters
        problematic_chars = FilenameSanitizationRules.get_problematic_chars_in_filename(original)
        
        # Detect transformations applied
        transformations = self._detect_transformations(original, sanitized, problematic_chars)
        
        # Generate warnings
        warnings = self._generate_warnings(original, sanitized, problematic_chars)
        
        # Create result object
        result = SanitizationResult(
            original=original,
            sanitized=sanitized,
            changed=(original != sanitized),
            processing_time_ms=processing_time_ms,
            problematic_chars=problematic_chars,
            transformations=transformations,
            warnings=warnings,
            timestamp=datetime.now()
        )
        
        # Update metrics
        self._update_metrics(result)
        
        # Log based on severity
        self._log_result(result, user_email, project_context)
        
        return result
    
    def _detect_transformations(
        self, 
        original: str, 
        sanitized: str, 
        problematic_chars: Dict[str, list]
    ) -> List[str]:
        """Detect what transformations were applied"""
        transformations = []
        
        if original != sanitized:
            if len(original) != len(sanitized):
                if len(sanitized) < len(original):
                    transformations.append("length_truncated")
                else:
                    transformations.append("length_expanded")
            
            if any(problematic_chars.values()):
                transformations.append("character_replacement")
            
            if original.lower() != sanitized.lower():
                transformations.append("case_normalization")
            
            # Check for specific patterns
            if '—' in original or '–' in original:
                transformations.append("unicode_dash_replacement")
            
            if ''' in original or ''' in original or '"' in original or '"' in original:
                transformations.append("unicode_quote_replacement")
            
            if any(ord(c) > 127 for c in original) and not any(ord(c) > 127 for c in sanitized):
                transformations.append("unicode_transliteration")
            
            if ' ' in original and '-' in sanitized:
                transformations.append("space_to_dash")
        
        return transformations
    
    def _generate_warnings(
        self, 
        original: str, 
        sanitized: str, 
        problematic_chars: Dict[str, list]
    ) -> List[str]:
        """Generate warnings for potential issues"""
        warnings = []
        
        # Check for significant changes
        if len(original) - len(sanitized) > 20:
            warnings.append(f"Filename significantly shortened (from {len(original)} to {len(sanitized)} chars)")
        
        # Check for fallback to default
        if sanitized == "archivo":
            warnings.append("Filename fell back to default 'archivo' - original may have been invalid")
        
        # Check for many problematic characters
        total_problematic = sum(len(chars) for chars in problematic_chars.values())
        if total_problematic > 10:
            warnings.append(f"High number of problematic characters detected ({total_problematic})")
        
        # Check for Supabase-specific issues
        if problematic_chars.get('supabase_problematic'):
            supabase_chars = set(problematic_chars['supabase_problematic'])
            if any(char in ['—', '–', ''', '''] for char in supabase_chars):
                warnings.append("Contains Unicode characters known to cause Supabase Storage errors")
        
        # Check for potential encoding issues
        if any(ord(c) > 255 for c in original):
            warnings.append("Contains high Unicode characters that may cause encoding issues")
        
        return warnings
    
    def _update_metrics(self, result: SanitizationResult) -> None:
        """Update internal metrics with sanitization result"""
        self.metrics['total_processed'] += 1
        if result.changed:
            self.metrics['total_changed'] += 1
        
        self.metrics['processing_time_total'] += result.processing_time_ms
        
        # Track character frequency
        for char_list in result.problematic_chars.values():
            for char in char_list:
                self.metrics['character_frequency'][char] += 1
        
        # Track transformation frequency
        for transformation in result.transformations:
            self.metrics['transformation_frequency'][transformation] += 1
    
    def _log_result(
        self, 
        result: SanitizationResult, 
        user_email: Optional[str] = None,
        project_context: Optional[str] = None
    ) -> None:
        """Log the sanitization result at appropriate level"""
        
        # Build context string
        context_parts = []
        if user_email:
            context_parts.append(f"user: {user_email}")
        if project_context:
            context_parts.append(f"project: {project_context}")
        context_str = f" ({', '.join(context_parts)})" if context_parts else ""
        
        if not result.changed:
            # No change needed - debug level
            self.logger.debug(f"📄 Filename unchanged: '{result.original}'{context_str}")
        
        elif result.warnings:
            # Has warnings - warning level
            self.logger.warning(
                f"⚠️ Filename sanitized with warnings: '{result.original}' → '{result.sanitized}'{context_str}\n"
                f"   Warnings: {'; '.join(result.warnings)}\n"
                f"   Transformations: {', '.join(result.transformations)}\n"
                f"   Processing time: {result.processing_time_ms:.2f}ms"
            )
        
        else:
            # Normal sanitization - info level
            self.logger.info(
                f"🧹 Filename sanitized: '{result.original}' → '{result.sanitized}'{context_str}\n"
                f"   Transformations: {', '.join(result.transformations) if result.transformations else 'none'}\n"
                f"   Processing time: {result.processing_time_ms:.2f}ms"
            )
        
        # Log problematic characters at debug level
        if any(result.problematic_chars.values()):
            char_details = []
            for category, chars in result.problematic_chars.items():
                if chars:
                    unique_chars = list(set(chars))
                    char_details.append(f"{category}: {unique_chars}")
            
            if char_details:
                self.logger.debug(f"🔍 Problematic characters detected: {'; '.join(char_details)}{context_str}")
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of sanitization metrics"""
        if self.metrics['total_processed'] > 0:
            avg_processing_time = self.metrics['processing_time_total'] / self.metrics['total_processed']
            change_rate = (self.metrics['total_changed'] / self.metrics['total_processed']) * 100
        else:
            avg_processing_time = 0
            change_rate = 0
        
        return {
            'total_processed': self.metrics['total_processed'],
            'total_changed': self.metrics['total_changed'],
            'change_rate_percent': round(change_rate, 2),
            'average_processing_time_ms': round(avg_processing_time, 2),
            'most_common_problematic_chars': dict(self.metrics['character_frequency'].most_common(10)),
            'most_common_transformations': dict(self.metrics['transformation_frequency'].most_common()),
            'total_processing_time_ms': round(self.metrics['processing_time_total'], 2)
        }
    
    def log_metrics_summary(self) -> None:
        """Log a summary of all sanitization metrics"""
        summary = self.get_metrics_summary()
        
        self.logger.info(
            f"📊 Filename Sanitization Metrics Summary:\n"
            f"   Total files processed: {summary['total_processed']}\n"
            f"   Files changed: {summary['total_changed']} ({summary['change_rate_percent']}%)\n"
            f"   Average processing time: {summary['average_processing_time_ms']}ms\n"
            f"   Total processing time: {summary['total_processing_time_ms']}ms\n"
            f"   Most common problematic chars: {summary['most_common_problematic_chars']}\n"
            f"   Most common transformations: {summary['most_common_transformations']}"
        )


# Global logger instance
_sanitization_logger = None

def get_filename_logger() -> FilenameSanitizationLogger:
    """Get the global filename sanitization logger instance"""
    global _sanitization_logger
    if _sanitization_logger is None:
        _sanitization_logger = FilenameSanitizationLogger()
    return _sanitization_logger

def log_sanitization_operation(
    original: str,
    sanitized: str,
    processing_time_ms: float,
    user_email: Optional[str] = None,
    project_context: Optional[str] = None
) -> SanitizationResult:
    """Convenience function to log a sanitization operation"""
    logger = get_filename_logger()
    return logger.log_sanitization(original, sanitized, processing_time_ms, user_email, project_context)

# Export main components
__all__ = [
    'SanitizationResult',
    'FilenameSanitizationLogger',
    'get_filename_logger',
    'log_sanitization_operation'
]






