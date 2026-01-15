# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/routes/__init__.py

Billing routes package.

Autor: DoxAI
Fecha: 2026-01-14
"""

from .admin_backfill import router as admin_backfill_router

__all__ = [
    "admin_backfill_router",
]
