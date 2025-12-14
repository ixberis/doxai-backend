# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/routes.py

Rutas de billing para paquetes de créditos.

Endpoint:
- GET /api/billing/credit-packages

Autor: DoxAI
Fecha: 2025-12-13
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

from .credit_packages import get_credit_packages, CreditPackage

router = APIRouter(
    prefix="/billing",
    tags=["billing"],
)


class CreditPackagesResponse(BaseModel):
    """Respuesta con lista de paquetes de créditos."""
    packages: List[CreditPackage]


@router.get(
    "/credit-packages",
    response_model=CreditPackagesResponse,
)
async def list_credit_packages():
    """
    Lista los paquetes de créditos disponibles para compra.
    
    Este endpoint es público (no requiere autenticación) ya que
    solo muestra información de precios.
    """
    packages = get_credit_packages()
    return CreditPackagesResponse(packages=packages)


# Fin del archivo
