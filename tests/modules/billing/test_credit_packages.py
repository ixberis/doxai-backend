# -*- coding: utf-8 -*-
"""
backend/tests/modules/billing/test_credit_packages.py

Tests para el endpoint de paquetes de créditos.

Autor: DoxAI
Fecha: 2025-12-13
"""

import pytest
from http import HTTPStatus


@pytest.mark.anyio
async def test_credit_packages_returns_200(async_client):
    """GET /api/billing/credit-packages debe retornar 200."""
    r = await async_client.get("/api/billing/credit-packages")
    assert r.status_code == HTTPStatus.OK


@pytest.mark.anyio
async def test_credit_packages_returns_list(async_client):
    """La respuesta debe contener una lista de paquetes."""
    r = await async_client.get("/api/billing/credit-packages")
    data = r.json()
    
    assert "packages" in data
    assert isinstance(data["packages"], list)
    assert len(data["packages"]) > 0


@pytest.mark.anyio
async def test_credit_packages_shape(async_client):
    """Cada paquete debe tener la estructura correcta."""
    r = await async_client.get("/api/billing/credit-packages")
    data = r.json()
    
    for pkg in data["packages"]:
        assert "id" in pkg
        assert "name" in pkg
        assert "credits" in pkg
        assert "price_cents" in pkg
        assert "currency" in pkg
        assert "popular" in pkg
        
        # Validar tipos
        assert isinstance(pkg["id"], str)
        assert isinstance(pkg["name"], str)
        assert isinstance(pkg["credits"], int)
        assert isinstance(pkg["price_cents"], int)
        assert isinstance(pkg["currency"], str)
        assert isinstance(pkg["popular"], bool)
        
        # Validar valores positivos
        assert pkg["credits"] > 0
        assert pkg["price_cents"] > 0


@pytest.mark.anyio
async def test_credit_packages_has_popular(async_client):
    """Al menos un paquete debe estar marcado como popular."""
    r = await async_client.get("/api/billing/credit-packages")
    data = r.json()
    
    popular_packages = [pkg for pkg in data["packages"] if pkg["popular"]]
    assert len(popular_packages) >= 1


@pytest.mark.anyio
async def test_credit_packages_unique_ids(async_client):
    """Cada paquete debe tener un ID único."""
    r = await async_client.get("/api/billing/credit-packages")
    data = r.json()
    
    ids = [pkg["id"] for pkg in data["packages"]]
    assert len(ids) == len(set(ids)), "Los IDs de paquetes deben ser únicos"


# Tests unitarios para get_package_by_id
def test_get_package_by_id_found():
    """get_package_by_id debe retornar el paquete correcto."""
    from app.modules.billing.credit_packages import get_package_by_id
    
    pkg = get_package_by_id("pkg_pro")
    assert pkg is not None
    assert pkg.id == "pkg_pro"
    assert pkg.credits == 500


def test_get_package_by_id_not_found():
    """get_package_by_id debe retornar None si no existe."""
    from app.modules.billing.credit_packages import get_package_by_id
    
    pkg = get_package_by_id("pkg_nonexistent")
    assert pkg is None


def test_get_credit_packages_returns_list():
    """get_credit_packages debe retornar lista no vacía."""
    from app.modules.billing.credit_packages import get_credit_packages
    
    packages = get_credit_packages()
    assert isinstance(packages, list)
    assert len(packages) > 0


# Fin del archivo
