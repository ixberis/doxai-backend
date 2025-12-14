
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/reconciliation/__init__.py

Submódulo de reconciliación - Conciliación de pagos con proveedores.

Autor: Ixchel Beristáin
Fecha: 26/10/2025 (ajustado 20/11/2025)
"""

from .core import (
    ReconciliationResult,
    reconcile_provider_transactions,
    find_discrepancies,
)
from .report import generate_reconciliation_report

__all__ = [
    "ReconciliationResult",
    "reconcile_provider_transactions",
    "find_discrepancies",
    "generate_reconciliation_report",
]

# Fin del archivo backend/app/modules/payments/facades/reconciliation/__init__.py
