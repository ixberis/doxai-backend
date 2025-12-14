# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/credit_packages.py

Configuración de paquetes de créditos (source of truth).

Los paquetes se definen aquí y son la única fuente de verdad
para precios y cantidades de créditos.

Autor: DoxAI
Fecha: 2025-12-13
"""

from __future__ import annotations

import os
import json
import logging
from typing import List
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CreditPackage(BaseModel):
    """Paquete de créditos disponible para compra."""
    id: str
    name: str
    credits: int
    price_cents: int
    currency: str = "MXN"
    popular: bool = False


# Paquetes por defecto (hardcoded)
DEFAULT_PACKAGES: List[dict] = [
    {
        "id": "pkg_starter",
        "name": "Starter",
        "credits": 100,
        "price_cents": 9900,  # $99.00 MXN
        "currency": "MXN",
        "popular": False,
    },
    {
        "id": "pkg_pro",
        "name": "Pro",
        "credits": 500,
        "price_cents": 39900,  # $399.00 MXN
        "currency": "MXN",
        "popular": True,
    },
    {
        "id": "pkg_enterprise",
        "name": "Enterprise",
        "credits": 2000,
        "price_cents": 149900,  # $1,499.00 MXN
        "currency": "MXN",
        "popular": False,
    },
]


def _validate_unique_ids(packages: List[dict]) -> List[dict]:
    """
    Valida que los IDs de paquetes sean únicos.
    
    Si hay duplicados, loggea warning y deduplica (mantiene el primero).
    
    Args:
        packages: Lista de diccionarios de paquetes
        
    Returns:
        Lista deduplicada de paquetes
    """
    seen_ids: set[str] = set()
    unique_packages: List[dict] = []
    
    for pkg in packages:
        pkg_id = pkg.get("id")
        if pkg_id in seen_ids:
            logger.warning(
                f"Duplicate package ID detected: '{pkg_id}'. "
                "Keeping first occurrence, ignoring duplicate."
            )
            continue
        seen_ids.add(pkg_id)
        unique_packages.append(pkg)
    
    return unique_packages


def get_credit_packages() -> List[CreditPackage]:
    """
    Obtiene la lista de paquetes de créditos.
    
    Primero intenta cargar desde CREDIT_PACKAGES_JSON env var,
    si no existe o falla el parsing, usa los paquetes por defecto.
    
    Returns:
        Lista de paquetes de créditos disponibles.
    """
    packages_json = os.getenv("CREDIT_PACKAGES_JSON")
    
    if packages_json:
        try:
            packages_data = json.loads(packages_json)
            if not isinstance(packages_data, list):
                logger.warning(
                    "CREDIT_PACKAGES_JSON must be a JSON array. "
                    "Using default packages."
                )
                packages_data = DEFAULT_PACKAGES
            else:
                # Validar IDs únicos
                packages_data = _validate_unique_ids(packages_data)
        except json.JSONDecodeError as e:
            logger.warning(
                f"Failed to parse CREDIT_PACKAGES_JSON: {e}. "
                "Using default packages."
            )
            packages_data = DEFAULT_PACKAGES
        except Exception as e:
            logger.warning(
                f"Unexpected error loading CREDIT_PACKAGES_JSON: {e}. "
                "Using default packages."
            )
            packages_data = DEFAULT_PACKAGES
    else:
        packages_data = DEFAULT_PACKAGES
    
    # Validar IDs únicos también para defaults
    packages_data = _validate_unique_ids(packages_data)
    
    return [CreditPackage(**pkg) for pkg in packages_data]


def get_package_by_id(package_id: str) -> CreditPackage | None:
    """
    Obtiene un paquete específico por ID.
    
    Args:
        package_id: ID del paquete (e.g., "pkg_pro")
    
    Returns:
        CreditPackage si existe, None si no.
    """
    packages = get_credit_packages()
    for pkg in packages:
        if pkg.id == package_id:
            return pkg
    return None


__all__ = [
    "CreditPackage",
    "get_credit_packages",
    "get_package_by_id",
    "DEFAULT_PACKAGES",
]
