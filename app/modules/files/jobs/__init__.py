# -*- coding: utf-8 -*-
"""
backend/app/modules/files/jobs/__init__.py

Jobs programados del módulo Files.
"""

from .reconcile_ghost_files_job import (
    JOB_ID as RECONCILE_GHOST_FILES_JOB_ID,
    reconcile_ghost_files_job,
    register_reconcile_ghost_files_job,
    FILES_RECONCILE_GHOSTS_ENABLED,
    FILES_RECONCILE_GHOSTS_INTERVAL_HOURS,
    FILES_RECONCILE_GHOSTS_BATCH_SIZE,
)

__all__ = [
    "RECONCILE_GHOST_FILES_JOB_ID",
    "reconcile_ghost_files_job",
    "register_reconcile_ghost_files_job",
    "FILES_RECONCILE_GHOSTS_ENABLED",
    "FILES_RECONCILE_GHOSTS_INTERVAL_HOURS",
    "FILES_RECONCILE_GHOSTS_BATCH_SIZE",
]
