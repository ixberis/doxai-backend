# -*- coding: utf-8 -*-
"""
backend/tests/modules/billing/test_credit_packages_validation.py

Tests para validación robusta de credit_packages:
- Logging en caso de JSON inválido
- Deduplicación de IDs duplicados

Autor: DoxAI
Fecha: 2025-12-13
"""

import pytest
import json
import logging
from unittest.mock import patch

from app.modules.billing.credit_packages import (
    get_credit_packages,
    get_package_by_id,
    _validate_unique_ids,
    DEFAULT_PACKAGES,
)


class TestValidateUniqueIds:
    """Tests para _validate_unique_ids."""

    def test_no_duplicates_returns_same_list(self):
        """Sin duplicados, retorna la misma lista."""
        packages = [
            {"id": "pkg_a", "name": "A"},
            {"id": "pkg_b", "name": "B"},
            {"id": "pkg_c", "name": "C"},
        ]
        result = _validate_unique_ids(packages)
        assert len(result) == 3
        assert [p["id"] for p in result] == ["pkg_a", "pkg_b", "pkg_c"]

    def test_duplicates_are_removed_and_logged(self, caplog):
        """Duplicados se eliminan y se loggea warning."""
        packages = [
            {"id": "pkg_a", "name": "A"},
            {"id": "pkg_a", "name": "A Duplicate"},  # Duplicado
            {"id": "pkg_b", "name": "B"},
        ]
        
        with caplog.at_level(logging.WARNING):
            result = _validate_unique_ids(packages)
        
        assert len(result) == 2
        assert [p["id"] for p in result] == ["pkg_a", "pkg_b"]
        # Primer pkg_a se mantiene (name="A")
        assert result[0]["name"] == "A"
        # Se loggeó warning
        assert "Duplicate package ID detected: 'pkg_a'" in caplog.text


class TestGetCreditPackagesValidation:
    """Tests para validación en get_credit_packages."""

    def test_invalid_json_logs_warning_and_uses_defaults(self, monkeypatch, caplog):
        """JSON inválido loggea warning y usa defaults."""
        monkeypatch.setenv("CREDIT_PACKAGES_JSON", "not valid json {{{")
        
        with caplog.at_level(logging.WARNING):
            packages = get_credit_packages()
        
        assert "Failed to parse CREDIT_PACKAGES_JSON" in caplog.text
        assert len(packages) == len(DEFAULT_PACKAGES)

    def test_json_not_array_logs_warning_and_uses_defaults(self, monkeypatch, caplog):
        """JSON que no es array loggea warning y usa defaults."""
        monkeypatch.setenv("CREDIT_PACKAGES_JSON", '{"not": "an array"}')
        
        with caplog.at_level(logging.WARNING):
            packages = get_credit_packages()
        
        assert "CREDIT_PACKAGES_JSON must be a JSON array" in caplog.text
        assert len(packages) == len(DEFAULT_PACKAGES)

    def test_valid_json_with_duplicates_deduplicates_and_logs(self, monkeypatch, caplog):
        """JSON válido con duplicados deduplica y loggea."""
        packages_data = [
            {"id": "dup", "name": "First", "credits": 100, "price_cents": 1000},
            {"id": "dup", "name": "Second", "credits": 200, "price_cents": 2000},
            {"id": "unique", "name": "Unique", "credits": 50, "price_cents": 500},
        ]
        monkeypatch.setenv("CREDIT_PACKAGES_JSON", json.dumps(packages_data))
        
        with caplog.at_level(logging.WARNING):
            packages = get_credit_packages()
        
        assert "Duplicate package ID detected: 'dup'" in caplog.text
        assert len(packages) == 2
        # Primer "dup" se mantiene
        dup_pkg = next(p for p in packages if p.id == "dup")
        assert dup_pkg.name == "First"
        assert dup_pkg.credits == 100

    def test_valid_json_without_duplicates(self, monkeypatch):
        """JSON válido sin duplicados funciona correctamente."""
        packages_data = [
            {"id": "custom_a", "name": "Custom A", "credits": 50, "price_cents": 4900},
            {"id": "custom_b", "name": "Custom B", "credits": 200, "price_cents": 19900},
        ]
        monkeypatch.setenv("CREDIT_PACKAGES_JSON", json.dumps(packages_data))
        
        packages = get_credit_packages()
        
        assert len(packages) == 2
        assert packages[0].id == "custom_a"
        assert packages[1].id == "custom_b"


class TestGetPackageById:
    """Tests para get_package_by_id."""

    def test_existing_package_returns_package(self):
        """Paquete existente retorna el paquete."""
        pkg = get_package_by_id("pkg_pro")
        assert pkg is not None
        assert pkg.id == "pkg_pro"
        assert pkg.credits == 500

    def test_nonexistent_package_returns_none(self):
        """Paquete inexistente retorna None."""
        pkg = get_package_by_id("pkg_fantasy")
        assert pkg is None


# Fin del archivo
