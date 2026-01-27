# -*- coding: utf-8 -*-
"""
backend/app/modules/files/jobs/__init__.py

Jobs programados del módulo Files.

Jobs incluidos:
1. reconcile_ghost_files_job: Detecta y archiva archivos fantasma (DB≠Storage)
2. retention_cleanup_job: Política de retención de archivos (closed→deleted)
"""

from .reconcile_ghost_files_job import (
    JOB_ID as RECONCILE_GHOST_FILES_JOB_ID,
    reconcile_ghost_files_job,
    register_reconcile_ghost_files_job,
    FILES_RECONCILE_GHOSTS_ENABLED,
    FILES_RECONCILE_GHOSTS_INTERVAL_HOURS,
    FILES_RECONCILE_GHOSTS_BATCH_SIZE,
)

from .retention_cleanup_job import (
    JOB_ID as RETENTION_CLEANUP_JOB_ID,
    retention_cleanup_job,
    register_retention_cleanup_job,
    FILES_RETENTION_ENABLED,
    FILES_RETENTION_INTERVAL_HOURS,
    FILES_RETENTION_GRACE_DAYS,
    FILES_RETENTION_DELETE_DAYS,
    FILES_RETENTION_BATCH_SIZE,
)

__all__ = [
    # Reconcile ghost files job
    "RECONCILE_GHOST_FILES_JOB_ID",
    "reconcile_ghost_files_job",
    "register_reconcile_ghost_files_job",
    "FILES_RECONCILE_GHOSTS_ENABLED",
    "FILES_RECONCILE_GHOSTS_INTERVAL_HOURS",
    "FILES_RECONCILE_GHOSTS_BATCH_SIZE",
    # Retention cleanup job
    "RETENTION_CLEANUP_JOB_ID",
    "retention_cleanup_job",
    "register_retention_cleanup_job",
    "FILES_RETENTION_ENABLED",
    "FILES_RETENTION_INTERVAL_HOURS",
    "FILES_RETENTION_GRACE_DAYS",
    "FILES_RETENTION_DELETE_DAYS",
    "FILES_RETENTION_BATCH_SIZE",
]
