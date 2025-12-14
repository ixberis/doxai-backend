# -*- coding: utf-8 -*-
"""
backend/app/shared/core/__init__.py

Core resources y utilities compartidos de DoxAI.
Gestión de recursos globales, caches, singletons y warm-up.

Autor: Ixchel Beristáin
Fecha: 24/10/2025
"""

from .resource_cache import (
    run_warmup_once,
    get_warmup_status,
    shutdown_all,
    get_http_client,
    retry_with_backoff,
    retry_get_with_backoff,
    retry_post_with_backoff,
    warmup_unstructured,
    ensure_table_model_loaded,
    get_table_agent,
    get_fast_parser,
    get_standard_language_config,
)

__all__ = [
    "run_warmup_once",
    "get_warmup_status",
    "shutdown_all",
    "get_http_client",
    "retry_with_backoff",
    "retry_get_with_backoff",
    "retry_post_with_backoff",
    "warmup_unstructured",
    "ensure_table_model_loaded",
    "get_table_agent",
    "get_fast_parser",
    "get_standard_language_config",
]
