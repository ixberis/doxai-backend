# -*- coding: utf-8 -*-
"""
backend/app/shared/utils/log_throttle.py

Rate-limited logging utilities to prevent log spam in production.

Provides:
- log_once_every: Log a message at most once per interval
- should_log_once_every: Check if we should log (for conditional blocks)

Usage:
    from app.shared.utils.log_throttle import log_once_every, should_log_once_every
    
    # Simple usage
    log_once_every("ip_security", 60, logger, logging.DEBUG, "Ignoring proxy headers for %s", ip)
    
    # Conditional usage
    if should_log_once_every(f"ip_security:{ip}", 60):
        logger.debug("Detailed message for %s", ip)

Author: DoxAI
Date: 2026-01-10
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

# Thread-safe cache for last log times
_log_cache: dict[str, float] = {}
_log_cache_lock = threading.Lock()

# Maximum cache size to prevent memory leaks (LRU-style cleanup)
_MAX_CACHE_SIZE = 10000


def _cleanup_cache_if_needed() -> None:
    """Remove oldest entries if cache exceeds max size."""
    if len(_log_cache) > _MAX_CACHE_SIZE:
        # Keep only the most recent half
        sorted_keys = sorted(_log_cache.keys(), key=lambda k: _log_cache[k])
        for key in sorted_keys[:_MAX_CACHE_SIZE // 2]:
            _log_cache.pop(key, None)


def should_log_once_every(key: str, seconds: float) -> bool:
    """
    Check if we should log for the given key.
    
    Returns True at most once per `seconds` interval for the same key.
    Thread-safe.
    
    Args:
        key: Unique identifier for this log source (e.g., "ip_security:10.0.0.1")
        seconds: Minimum interval between logs for this key
    
    Returns:
        True if enough time has passed since last log for this key
    """
    now = time.monotonic()
    
    with _log_cache_lock:
        last_time = _log_cache.get(key)
        
        if last_time is None or (now - last_time) >= seconds:
            _log_cache[key] = now
            _cleanup_cache_if_needed()
            return True
        
        return False


def log_once_every(
    key: str,
    seconds: float,
    logger: logging.Logger,
    level: int,
    msg: str,
    *args: Any,
    **kwargs: Any,
) -> bool:
    """
    Log a message at most once per interval.
    
    Thread-safe. Uses monotonic clock to avoid issues with clock adjustments.
    
    Args:
        key: Unique identifier for this log source
        seconds: Minimum interval between logs for this key
        logger: Logger instance to use
        level: Logging level (logging.DEBUG, logging.INFO, etc.)
        msg: Log message (may contain % formatting)
        *args: Arguments for message formatting
        **kwargs: Additional kwargs for logger (e.g., extra, exc_info)
    
    Returns:
        True if the log was emitted, False if throttled
    
    Example:
        log_once_every(
            "redis_metrics_nothing", 
            60, 
            logger, 
            logging.DEBUG, 
            "RedisHttpMetricsStore: nothing to flush"
        )
    """
    if not should_log_once_every(key, seconds):
        return False
    
    # Only log if the level is enabled (avoid unnecessary formatting)
    if logger.isEnabledFor(level):
        logger.log(level, msg, *args, **kwargs)
        return True
    
    return False


def clear_log_cache() -> None:
    """Clear the log throttle cache. Useful for testing."""
    with _log_cache_lock:
        _log_cache.clear()


def get_cache_size() -> int:
    """Get current cache size. Useful for monitoring."""
    with _log_cache_lock:
        return len(_log_cache)
