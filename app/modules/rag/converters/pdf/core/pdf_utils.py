# -*- coding: utf-8 -*-
"""
PDF Utilities - Common PDF operations and helpers.
"""

from __future__ import annotations
from typing import Set
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def get_pdf_page_count(pdf_path: Path) -> int:
    """Gets total number of pages in PDF."""
    try:
        import PyPDF2
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            return len(reader.pages)
    except Exception as e:
        logger.error(f"❌ Error getting PDF pages: {e}")
        return 1


def get_remaining_pages(pdf_path: Path, processed_pages: Set[int]) -> Set[int]:
    """Gets unprocessed pages."""
    try:
        total_pages = get_pdf_page_count(pdf_path)
        all_pages = set(range(1, total_pages + 1))
        return all_pages - processed_pages
    except Exception:
        return set()






