# -*- coding: utf-8 -*-
"""
backend/app/shared/scheduler/jobs/__init__.py

Jobs programados del sistema.

Autor: DoxAI
Fecha: 2025-11-05
"""

from .cache_cleanup_job import cleanup_expired_cache, register_cache_cleanup_job

# Importar job de reconciliación de archivos fantasma
try:
    from app.modules.files.jobs import (
        RECONCILE_GHOST_FILES_JOB_ID,
        reconcile_ghost_files_job,
        register_reconcile_ghost_files_job,
        FILES_RECONCILE_GHOSTS_ENABLED,
        FILES_RECONCILE_GHOSTS_INTERVAL_HOURS,
        FILES_RECONCILE_GHOSTS_BATCH_SIZE,
    )
    _reconcile_job_available = True
except ImportError:
    _reconcile_job_available = False
    RECONCILE_GHOST_FILES_JOB_ID = None
    reconcile_ghost_files_job = None
    register_reconcile_ghost_files_job = None
    FILES_RECONCILE_GHOSTS_ENABLED = False
    FILES_RECONCILE_GHOSTS_INTERVAL_HOURS = 6
    FILES_RECONCILE_GHOSTS_BATCH_SIZE = 500

__all__ = [
    "cleanup_expired_cache",
    "register_cache_cleanup_job",
    # Reconcile ghost files job
    "RECONCILE_GHOST_FILES_JOB_ID",
    "reconcile_ghost_files_job",
    "register_reconcile_ghost_files_job",
    "FILES_RECONCILE_GHOSTS_ENABLED",
    "FILES_RECONCILE_GHOSTS_INTERVAL_HOURS",
    "FILES_RECONCILE_GHOSTS_BATCH_SIZE",
]
