
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/schemas/wallet_schemas.py

Esquemas para exponer información de la wallet del usuario.

Autor: Ixchel Beristain
Fecha: 2025-11-21 (v3)
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class WalletOut(BaseModel):
    """
    Representación de la wallet de un usuario.

    NOTA:
    - balance, balance_reserved y balance_available se calculan
      en servicios, no aquí.
    """

    id: int = Field(description="ID interno de la wallet.")
    user_id: str = Field(description="ID del usuario dueño de la wallet.")

    balance: int = Field(
        ge=0,
        description="Balance total de créditos (ledger).",
    )
    balance_reserved: int = Field(
        ge=0,
        description="Créditos reservados (bloqueados) por operaciones en curso.",
    )
    balance_available: int = Field(
        ge=0,
        description="Créditos disponibles = balance - balance_reserved.",
    )


__all__ = ["WalletOut"]

# Fin del archivo backend/app/modules/payments/schemas/wallet_schemas.py