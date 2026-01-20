# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/storage/safe_filename.py

SSOT canonical function for creating safe storage filenames.

Accepts ANY user-provided filename (accents, emojis, symbols, etc.) and
returns a Supabase Storage-safe key while preserving the original for display.

Author: Ixchel Beristain
Created: 2026-01-20
"""

import re
import unicodedata
from typing import Optional
from uuid import UUID

# Mapping of common Unicode characters to ASCII equivalents
_UNICODE_REPLACEMENTS: dict[str, str] = {
    # Typographic dashes
    "—": "-",  # em-dash
    "–": "-",  # en-dash
    "―": "-",  # horizontal bar
    "‒": "-",  # figure dash
    # Quotation marks
    "'": "",   # left single
    "'": "",   # right single
    """: "",   # left double
    """: "",   # right double
    "«": "",   # left guillemet
    "»": "",   # right guillemet
    # Whitespace variants
    "\u00a0": "_",  # non-breaking space
    "\u2003": "_",  # em space
    "\u2002": "_",  # en space
    "\u2009": "_",  # thin space
    # Common special chars
    "…": "...",
    "•": "-",
    "™": "",
    "®": "",
    "©": "",
    "°": "",
    "±": "",
    "×": "x",
    "÷": "-",
    "№": "n",
}

# Extension mapping from MIME type to extension
_MIME_TO_EXT: dict[str, str] = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.oasis.opendocument.text": ".odt",
    "application/vnd.oasis.opendocument.spreadsheet": ".ods",
    "application/vnd.oasis.opendocument.presentation": ".odp",
    "text/plain": ".txt",
    "text/csv": ".csv",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "application/zip": ".zip",
    "application/octet-stream": ".bin",
}


def make_safe_storage_filename(
    original_name: str,
    file_id: Optional[UUID] = None,
    mime_type: Optional[str] = None,
    max_length: int = 120,
) -> str:
    """
    Create a safe filename for Supabase Storage from any user-provided name.
    
    SSOT Guarantees:
    - Always returns a non-empty, valid storage key
    - Only contains: [a-z0-9._-]
    - Preserves file extension when possible
    - Never blocks or rejects user input
    
    Args:
        original_name: User-provided filename (can contain anything)
        file_id: Optional UUID for fallback naming
        mime_type: Optional MIME type for extension fallback
        max_length: Maximum base name length (excluding extension)
    
    Returns:
        Safe filename string suitable for Supabase Storage
    
    Examples:
        >>> make_safe_storage_filename("Anexo—Términos y Condiciones (Rev. A).DoCx")
        "anexo-terminos-y-condiciones-rev.-a.docx"
        
        >>> make_safe_storage_filename("📄🔥.pdf")
        "file.pdf"
        
        >>> make_safe_storage_filename("!!!###.txt")
        "file.txt"
    """
    if not original_name or not original_name.strip():
        # Fallback for empty input
        ext = _get_extension_from_mime(mime_type)
        return _build_fallback_name(file_id, ext)
    
    # 1. Normalize Unicode (NFKD decomposes characters)
    name = unicodedata.normalize("NFKD", original_name.strip())
    
    # 2. Separate base and extension
    base, ext = _split_extension(name)
    
    # 3. Process the base name
    safe_base = _sanitize_base(base)
    
    # 4. Process the extension
    safe_ext = _sanitize_extension(ext, mime_type)
    
    # 5. Handle empty base after sanitization
    if not safe_base or safe_base in ("_", "-", "."):
        safe_base = _build_fallback_base(file_id)
    
    # 6. Truncate if needed (preserve extension)
    if len(safe_base) > max_length:
        safe_base = safe_base[:max_length].rstrip("-_.")
    
    # 7. Final assembly
    result = f"{safe_base}{safe_ext}" if safe_ext else safe_base
    
    # 8. Final validation - ensure non-empty
    if not result or result == ".":
        result = _build_fallback_name(file_id, safe_ext or ".bin")
    
    return result


def _split_extension(name: str) -> tuple[str, str]:
    """Split filename into base and extension."""
    # Find last dot that's not at the start
    last_dot = name.rfind(".")
    if last_dot > 0:
        ext = name[last_dot:]
        base = name[:last_dot]
        # Validate extension is reasonable (not too long, alphanumeric)
        if len(ext) <= 10 and ext[1:].replace("_", "").isalnum():
            return base, ext.lower()
    return name, ""


def _sanitize_base(base: str) -> str:
    """Sanitize the base filename (without extension)."""
    # Step 1: Apply Unicode replacements
    for char, replacement in _UNICODE_REPLACEMENTS.items():
        base = base.replace(char, replacement)
    
    # Step 2: Transliterate accented characters to ASCII
    # NFKD normalization + remove combining marks
    base = unicodedata.normalize("NFKD", base)
    base = "".join(c for c in base if unicodedata.category(c) != "Mn")
    
    # Step 3: Convert to lowercase
    base = base.lower()
    
    # Step 4: Replace problematic characters with hyphens
    # Allow only: a-z, 0-9, dot, underscore, hyphen
    base = re.sub(r"[^a-z0-9._-]", "-", base)
    
    # Step 5: Collapse multiple hyphens/underscores
    base = re.sub(r"[-_]+", "-", base)
    
    # Step 6: Remove leading/trailing hyphens and dots
    base = base.strip("-_.")
    
    return base


def _sanitize_extension(ext: str, mime_type: Optional[str] = None) -> str:
    """Sanitize or derive a valid extension."""
    if ext:
        # Clean extension: lowercase, alphanumeric only
        clean_ext = re.sub(r"[^a-z0-9]", "", ext.lower())
        if clean_ext:
            return f".{clean_ext}"
    
    # Fallback to MIME type
    return _get_extension_from_mime(mime_type)


def _get_extension_from_mime(mime_type: Optional[str]) -> str:
    """Get extension from MIME type."""
    if mime_type:
        return _MIME_TO_EXT.get(mime_type.lower(), ".bin")
    return ".bin"


def _build_fallback_base(file_id: Optional[UUID]) -> str:
    """Build fallback base name."""
    if file_id:
        return f"file-{str(file_id)[:8]}"
    return "file"


def _build_fallback_name(file_id: Optional[UUID], ext: str) -> str:
    """Build complete fallback filename."""
    base = _build_fallback_base(file_id)
    if not ext.startswith("."):
        ext = f".{ext}" if ext else ".bin"
    return f"{base}{ext}"


__all__ = ["make_safe_storage_filename"]

# End of file backend/app/modules/files/services/storage/safe_filename.py
