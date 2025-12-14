
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/receipts/__init__.py

Submódulo de recibos - Generación y gestión de recibos PDF.

Autor: Ixchel Beristáin
Fecha: 26/10/2025 (ajustado 20/11/2025)
"""

from .generator import generate_receipt
from .signer import get_receipt_url
from .eligibility import regenerate_receipt

__all__ = [
    "generate_receipt",
    "get_receipt_url",
    "regenerate_receipt",
]

# Fin del archivo backend/app/modules/payments/facades/receipts/__init__.py