# -*- coding: utf-8 -*-
"""
backend/app/shared/scheduler/__init__.py

Sistema de jobs programados usando APScheduler.

Autor: DoxAI
Fecha: 2025-11-05
"""

from .scheduler_service import SchedulerService, get_scheduler

__all__ = [
    "SchedulerService",
    "get_scheduler",
]
