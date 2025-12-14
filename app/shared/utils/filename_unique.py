# -*- coding: utf-8 -*-
"""
backend/app/utils/filename_unique.py

Utilities for ensuring filename uniqueness
"""

import os
from typing import Callable, Awaitable, Union
from .filename_core import sanitize_filename_for_storage


async def ensure_unique_filename(
    original_name: str, 
    exists_fn: Callable[[str], Union[bool, Awaitable[bool]]], 
    strict_mode: bool = False,
    max_retries: int = 100
) -> str:
    """
    Ensures a filename is unique by checking against an existence function
    and appending a counter if needed (filename-1.ext, filename-2.ext, etc.)
    
    Args:
        original_name: Original filename
        exists_fn: Function that returns True if filename exists
        strict_mode: Whether to use strict sanitization
        max_retries: Maximum number of retries before adding timestamp
        
    Returns:
        Unique sanitized filename
    """
    import asyncio
    import time
    
    # First sanitize the filename
    sanitized = sanitize_filename_for_storage(original_name, strict_mode)
    
    # Extract base and extension
    base, ext = os.path.splitext(sanitized)
    
    candidate = sanitized
    counter = 1
    
    # Check if the sanitized name already exists
    while counter <= max_retries:
        # Handle both sync and async exists functions
        if asyncio.iscoroutinefunction(exists_fn):
            exists = await exists_fn(candidate)
        else:
            exists = exists_fn(candidate)
            
        if not exists:
            break
            
        candidate = f"{base}-{counter}{ext}"
        counter += 1
    
    if counter > max_retries:
        # If we've exceeded max retries, add timestamp
        timestamp = int(time.time() * 1000)  # milliseconds
        candidate = f"{base}-{timestamp}{ext}"
    
    return candidate


def ensure_unique_filename_sync(
    original_name: str, 
    existing_names: list[str], 
    strict_mode: bool = False,
    max_retries: int = 100
) -> str:
    """
    Synchronous version for cases where you have a list of existing names
    
    Args:
        original_name: Original filename
        existing_names: List of existing filenames to check against
        strict_mode: Whether to use strict sanitization
        max_retries: Maximum number of retries before adding timestamp
        
    Returns:
        Unique sanitized filename
    """
    import time
    
    # First sanitize the filename
    sanitized = sanitize_filename_for_storage(original_name, strict_mode)
    
    # Extract base and extension
    base, ext = os.path.splitext(sanitized)
    
    candidate = sanitized
    counter = 1
    
    # Check if the sanitized name already exists
    while candidate in existing_names and counter <= max_retries:
        candidate = f"{base}-{counter}{ext}"
        counter += 1
    
    if counter > max_retries:
        # If we've exceeded max retries, add timestamp
        timestamp = int(time.time() * 1000)  # milliseconds
        candidate = f"{base}-{timestamp}{ext}"
    
    return candidate


# Export functions
__all__ = [
    'ensure_unique_filename',
    'ensure_unique_filename_sync'
]






