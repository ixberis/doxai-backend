# -*- coding: utf-8 -*-
"""
backend/tests/modules/payments/test_bloque_b_trusted_proxy.py

Tests para BLOQUE B: Trusted proxy headers (X-Forwarded-For).

Autor: DoxAI
Fecha: 2025-12-13
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from app.modules.payments.services.webhooks.client_ip import (
    get_client_ip,
    get_client_ip_for_rate_limit,
)


class MockRequest:
    """Mock de Starlette Request para tests."""
    
    def __init__(self, client_host: str = "127.0.0.1", headers: dict = None):
        self.headers = headers or {}
        self.client = MagicMock()
        self.client.host = client_host


class TestGetClientIpWithoutTrustProxy:
    """Tests cuando TRUST_PROXY_HEADERS=false (default)."""

    def test_uses_client_host_by_default(self):
        """Sin flag, usa request.client.host."""
        with patch.dict("os.environ", {"TRUST_PROXY_HEADERS": "false"}, clear=False):
            request = MockRequest(client_host="192.168.1.100")
            result = get_client_ip(request)
            assert result == "192.168.1.100"

    def test_ignores_xff_when_not_trusted(self):
        """Sin flag, ignora X-Forwarded-For."""
        with patch.dict("os.environ", {"TRUST_PROXY_HEADERS": "false"}, clear=False):
            request = MockRequest(
                client_host="10.0.0.1",
                headers={"x-forwarded-for": "203.0.113.50, 70.41.3.18"}
            )
            result = get_client_ip(request)
            # Debe usar client.host, NO X-Forwarded-For
            assert result == "10.0.0.1"

    def test_ignores_x_real_ip_when_not_trusted(self):
        """Sin flag, ignora X-Real-IP."""
        with patch.dict("os.environ", {"TRUST_PROXY_HEADERS": "false"}, clear=False):
            request = MockRequest(
                client_host="10.0.0.2",
                headers={"x-real-ip": "203.0.113.75"}
            )
            result = get_client_ip(request)
            assert result == "10.0.0.2"

    def test_returns_unknown_when_no_client(self):
        """Sin client, retorna 'unknown'."""
        with patch.dict("os.environ", {"TRUST_PROXY_HEADERS": "false"}, clear=False):
            request = MockRequest()
            request.client = None
            result = get_client_ip(request)
            assert result == "unknown"


class TestGetClientIpWithTrustProxy:
    """Tests cuando TRUST_PROXY_HEADERS=true."""

    def test_uses_xff_first_ip(self):
        """Con flag, usa primer IP de X-Forwarded-For."""
        with patch.dict("os.environ", {"TRUST_PROXY_HEADERS": "true"}, clear=False):
            request = MockRequest(
                client_host="10.0.0.1",
                headers={"x-forwarded-for": "203.0.113.50, 70.41.3.18, 10.0.0.1"}
            )
            result = get_client_ip(request)
            # Primer IP es el cliente original
            assert result == "203.0.113.50"

    def test_trims_whitespace_from_xff(self):
        """Limpia espacios de X-Forwarded-For."""
        with patch.dict("os.environ", {"TRUST_PROXY_HEADERS": "true"}, clear=False):
            request = MockRequest(
                client_host="10.0.0.1",
                headers={"x-forwarded-for": "  203.0.113.50  , 70.41.3.18"}
            )
            result = get_client_ip(request)
            assert result == "203.0.113.50"

    def test_uses_x_real_ip_as_fallback(self):
        """Con flag y sin XFF, usa X-Real-IP."""
        with patch.dict("os.environ", {"TRUST_PROXY_HEADERS": "true"}, clear=False):
            request = MockRequest(
                client_host="10.0.0.1",
                headers={"x-real-ip": "203.0.113.75"}
            )
            result = get_client_ip(request)
            assert result == "203.0.113.75"

    def test_falls_back_to_client_host(self):
        """Sin headers de proxy, usa client.host."""
        with patch.dict("os.environ", {"TRUST_PROXY_HEADERS": "true"}, clear=False):
            request = MockRequest(client_host="192.168.1.50")
            result = get_client_ip(request)
            assert result == "192.168.1.50"

    def test_xff_priority_over_x_real_ip(self):
        """X-Forwarded-For tiene prioridad sobre X-Real-IP."""
        with patch.dict("os.environ", {"TRUST_PROXY_HEADERS": "true"}, clear=False):
            request = MockRequest(
                client_host="10.0.0.1",
                headers={
                    "x-forwarded-for": "203.0.113.50",
                    "x-real-ip": "203.0.113.75"
                }
            )
            result = get_client_ip(request)
            assert result == "203.0.113.50"


class TestGetClientIpForRateLimit:
    """Tests para versión de rate limiting."""

    def test_same_behavior_as_get_client_ip(self):
        """Misma lógica que get_client_ip."""
        with patch.dict("os.environ", {"TRUST_PROXY_HEADERS": "true"}, clear=False):
            request = MockRequest(
                client_host="10.0.0.1",
                headers={"x-forwarded-for": "203.0.113.50"}
            )
            result = get_client_ip_for_rate_limit(request)
            assert result == "203.0.113.50"

    def test_respects_trust_flag_false(self):
        """Respeta flag TRUST_PROXY_HEADERS=false."""
        with patch.dict("os.environ", {"TRUST_PROXY_HEADERS": "false"}, clear=False):
            request = MockRequest(
                client_host="10.0.0.1",
                headers={"x-forwarded-for": "203.0.113.50"}
            )
            result = get_client_ip_for_rate_limit(request)
            assert result == "10.0.0.1"


class TestTrustProxyFlagVariations:
    """Tests para variaciones del flag TRUST_PROXY_HEADERS."""

    @pytest.mark.parametrize("value", ["true", "TRUE", "True", "1", "yes", "YES"])
    def test_truthy_values(self, value):
        """Valores que activan el flag."""
        with patch.dict("os.environ", {"TRUST_PROXY_HEADERS": value}, clear=False):
            request = MockRequest(
                client_host="10.0.0.1",
                headers={"x-forwarded-for": "203.0.113.50"}
            )
            result = get_client_ip(request)
            assert result == "203.0.113.50"

    @pytest.mark.parametrize("value", ["false", "FALSE", "0", "no", "", "anything"])
    def test_falsy_values(self, value):
        """Valores que desactivan el flag."""
        with patch.dict("os.environ", {"TRUST_PROXY_HEADERS": value}, clear=False):
            request = MockRequest(
                client_host="10.0.0.1",
                headers={"x-forwarded-for": "203.0.113.50"}
            )
            result = get_client_ip(request)
            assert result == "10.0.0.1"

    def test_missing_env_var_defaults_to_false(self):
        """Sin variable, default es false (seguro)."""
        import os
        # Asegurar que no existe la variable
        env_backup = os.environ.get("TRUST_PROXY_HEADERS")
        if "TRUST_PROXY_HEADERS" in os.environ:
            del os.environ["TRUST_PROXY_HEADERS"]
        
        try:
            request = MockRequest(
                client_host="10.0.0.1",
                headers={"x-forwarded-for": "203.0.113.50"}
            )
            result = get_client_ip(request)
            # Default es false, ignora XFF
            assert result == "10.0.0.1"
        finally:
            if env_backup is not None:
                os.environ["TRUST_PROXY_HEADERS"] = env_backup
