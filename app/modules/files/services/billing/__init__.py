# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/billing/__init__.py

Submódulo de billing para Files.

Contiene:
- FilesBillingService: Servicio para consumo de créditos por operaciones Files

Autor: DoxAI
Fecha: 2026-01-26
"""

from .files_billing_service import (
    FilesBillingService,
    FilesBillingConfig,
    calculate_credits_for_file,
)

__all__ = [
    "FilesBillingService",
    "FilesBillingConfig",
    "calculate_credits_for_file",
]
