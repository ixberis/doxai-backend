# -*- coding: utf-8 -*-
"""
backend/app/shared/scheduler/jobs/__init__.py

Jobs programados del sistema.

Autor: DoxAI
Fecha: 2025-11-05
"""

from .cache_cleanup_job import cleanup_expired_cache, register_cache_cleanup_job

__all__ = [
    "cleanup_expired_cache",
    "register_cache_cleanup_job",
]
