# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_tabular_extractor_refactored.py

Main interface for specialized tabular data extraction from PDFs.
Coordinates all extraction, deduplication, and format conversion operations.

Author: Ixchel Beristain Mendoza
Refactored: 28/09/2025
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
import logging

from .pdf_table_pdfplumber_extractor import extract_tables_pdfplumber
from .pdf_table_deduplication_service import normalize_and_dedupe_tables, dedupe_tables_by_content_hash
from .pdf_table_extraction_coordinator import extract_tables_specialized, validate_extraction_parameters
from .pdf_table_format_converter import convert_to_unstructured_format

logger = logging.getLogger(__name__)

# Export main functions for backward compatibility
# Note: _dedupe_tables_by_content_hash is aliased to dedupe_tables_by_content_hash for tests
_dedupe_tables_by_content_hash = dedupe_tables_by_content_hash

__all__ = [
    'extract_tables_pdfplumber',
    'normalize_and_dedupe_tables', 
    'extract_tables_specialized',
    'convert_to_unstructured_format',
    'dedupe_tables_by_content_hash',
    '_dedupe_tables_by_content_hash'
]






