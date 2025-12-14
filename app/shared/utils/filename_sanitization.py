# -*- coding: utf-8 -*-
"""
backend/app/utils/filename_sanitization.py

Compatibility module for filename sanitization.
Re-exports core sanitization functionality to maintain backward compatibility.

This module serves as an alias to the core functionality while maintaining
clean separation of concerns.

Autor: Ixchel Beristain  
Creado: 25/09/2025
"""

# Import from core module
from app.shared.utils.filename_core import (
    sanitize_filename_for_storage,
    validate_filename_basic,
    extract_file_extension,
    normalize_filename_unicode,
    collapse_whitespace,
    remove_problematic_chars
)

# Re-export for compatibility
__all__ = [
    'sanitize_filename_for_storage',
    'validate_filename_basic',
    'extract_file_extension',
    'normalize_filename_unicode', 
    'collapse_whitespace',
    'remove_problematic_chars'
]






