
# -*- coding: utf-8 -*-
"""
backend/tests/modules/payments/test_bloque_a_railway_readiness.py

Tests para BLOQUE A: Railway readiness - httpx async, timeouts, retries.

Autor: Ixchel Beristain
Fecha: 2025-12-13
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from app.modules.payments.services.webhooks.signature_verification import (
    _is_transient_error,
    _get_paypal_access_token_async,
    _clear_token_cache,
    _get_cached_token,
    _set_cached_token,
    _get_backoff_for_status,
    _reset_paypal_clients,
    _get_paypal_clients_count,
    get_paypal_token_client,
    get_paypal_verify_client,
    close_paypal_http_clients,
    PAYPAL_TOKEN_TIMEOUT,
    PAYPAL_VERIFY_TIMEOUT,
    PAYPAL_HTTP_LIMITS,
    TRANSIENT_HTTP_ERRORS,
    MAX_TRANSIENT_RETRIES,
    RETRY_BACKOFF_BASE,
    RETRY_BACKOFF_429,
    verify_paypal_signature_via_api,
)


class TestTimeoutConfiguration:
    """Tests para configuración de timeouts."""

    def test_paypal_token_timeout_has_explicit_values(self):
        """Token timeout tiene valores explícitos (A+2)."""
        assert PAYPAL_TOKEN_TIMEOUT.connect == 5.0
        assert PAYPAL_TOKEN_TIMEOUT.read == 10.0
        assert PAYPAL_TOKEN_TIMEOUT.write == 10.0  # A+2: write también definido
        assert PAYPAL_TOKEN_TIMEOUT.pool == 5.0

    def test_paypal_verify_timeout_has_explicit_values(self):
        """Verify timeout tiene valores explícitos más largos (A+2)."""
        assert PAYPAL_VERIFY_TIMEOUT.connect == 5.0
        assert PAYPAL_VERIFY_TIMEOUT.read == 15.0
        assert PAYPAL_VERIFY_TIMEOUT.write == 15.0  # A+2: write también definido
        assert PAYPAL_VERIFY_TIMEOUT.pool == 5.0

    def test_transient_errors_include_429_502_503_504(self):
        """Errores transitorios incluyen 429 (A+3), 502, 503, 504."""
        assert 429 in TRANSIENT_HTTP_ERRORS  # A+3: 429 es transitorio
        assert 502 in TRANSIENT_HTTP_ERRORS
        assert 503 in TRANSIENT_HTTP_ERRORS
        assert 504 in TRANSIENT_HTTP_ERRORS
        assert 500 not in TRANSIENT_HTTP_ERRORS
        assert 400 not in TRANSIENT_HTTP_ERRORS

    def test_http_limits_configured(self):
        """Límites HTTP para connection pooling (A+1)."""
        assert PAYPAL_HTTP_LIMITS.max_keepalive_connections == 20
        assert PAYPAL_HTTP_LIMITS.max_connections == 50
        assert PAYPAL_HTTP_LIMITS.keepalive_expiry == 30.0

    def test_max_transient_retries_is_1(self):
        """Máximo de reintentos es 1 (total 2 intentos)."""
        assert MAX_TRANSIENT_RETRIES == 1


class TestTransientErrorDetection:
    """Tests para detección de errores transitorios."""

    def test_502_is_transient(self):
        assert _is_transient_error(502) is True

    def test_503_is_transient(self):
        assert _is_transient_error(503) is True

    def test_504_is_transient(self):
        assert _is_transient_error(504) is True

    def test_500_is_not_transient(self):
        """500 Internal Server Error no es transitorio (bug del servidor)."""
        assert _is_transient_error(500) is False

    def test_400_is_not_transient(self):
        """400 Bad Request no es transitorio (error del cliente)."""
        assert _is_transient_error(400) is False

    def test_401_is_not_transient(self):
        """401 Unauthorized no es transitorio."""
        assert _is_transient_error(401) is False

    def test_200_is_not_transient(self):
        """200 OK no es transitorio."""
        assert _is_transient_error(200) is False

    def test_429_is_transient(self):
        """429 Rate Limited es transitorio (A+3)."""
        assert _is_transient_error(429) is True


class TestBackoffCalculation:
    """Tests para cálculo de backoff según tipo de error (A+3)."""

    def test_429_uses_larger_backoff(self):
        """429 usa backoff mayor que otros errores."""
        backoff_429 = _get_backoff_for_status(429, 0)
        backoff_502 = _get_backoff_for_status(502, 0)
        assert backoff_429 == RETRY_BACKOFF_429  # 2.0s
        assert backoff_502 == RETRY_BACKOFF_BASE  # 0.5s
        assert backoff_429 > backoff_502

    def test_backoff_exponential(self):
        """Backoff crece exponencialmente con intentos."""
        b0 = _get_backoff_for_status(502, 0)
        b1 = _get_backoff_for_status(502, 1)
        b2 = _get_backoff_for_status(502, 2)
        assert b1 == b0 * 2
        assert b2 == b0 * 4

    def test_429_backoff_exponential(self):
        """Backoff de 429 también crece exponencialmente."""
        b0 = _get_backoff_for_status(429, 0)
        b1 = _get_backoff_for_status(429, 1)
        assert b1 == b0 * 2  # 4.0s


class TestHttpClientSingleton:
    """Tests para cliente HTTP singleton (A+1)."""

    def setup_method(self):
        """Reset clientes antes de cada test."""
        _reset_paypal_clients()

    def test_token_client_returns_same_instance(self):
        """Mismo key (token) retorna mismo cliente."""
        client1 = get_paypal_token_client()
        client2 = get_paypal_token_client()
        assert client1 is client2

    def test_different_clients_for_token_and_verify(self):
        """Token y verify usan clientes diferentes."""
        client_token = get_paypal_token_client()
        client_verify = get_paypal_verify_client()
        assert client_token is not client_verify
        assert _get_paypal_clients_count() == 2

    def test_client_is_async_client_instance(self):
        """Cliente es instancia de httpx.AsyncClient."""
        client = get_paypal_token_client()
        assert isinstance(client, httpx.AsyncClient)

    @pytest.mark.asyncio
    async def test_close_clients_clears_registry(self):
        """Cerrar clientes limpia el registro."""
        _ = get_paypal_token_client()
        _ = get_paypal_verify_client()
        assert _get_paypal_clients_count() == 2
        
        await close_paypal_http_clients()
        assert _get_paypal_clients_count() == 0
        
        # Después de cerrar, nuevo get crea nuevo cliente
        client_new = get_paypal_token_client()
        assert client_new is not None
        assert _get_paypal_clients_count() == 1


class TestTokenCache:
    """Tests para cache de tokens con TTL."""

    def setup_method(self):
        """Limpiar cache antes de cada test."""
        _clear_token_cache()

    def test_set_and_get_token(self):
        """Puede guardar y recuperar token."""
        _set_cached_token("test_key", "test_token", expires_in=3600)
        result = _get_cached_token("test_key")
        assert result == "test_token"

    def test_returns_none_for_missing_key(self):
        """Devuelve None si la clave no existe."""
        result = _get_cached_token("nonexistent")
        assert result is None

    def test_expired_token_returns_none(self, monkeypatch):
        """Token expirado devuelve None (usando mock de time)."""
        import time as time_module
        from app.modules.payments.services.webhooks import signature_verification as sv
        
        # Usar mock de time para simular expiración sin esperar
        current_time = 1000.0
        monkeypatch.setattr(sv.time, "time", lambda: current_time)
        
        # Guardar token (expires_in=120 → TTL real = max(120-60, 60) = 60s)
        _set_cached_token("expire_test", "token", expires_in=120)
        
        # Token válido antes de expirar
        result = _get_cached_token("expire_test")
        assert result == "token"
        
        # Avanzar tiempo más allá del TTL (60s)
        current_time = 1061.0
        monkeypatch.setattr(sv.time, "time", lambda: current_time)
        
        result = _get_cached_token("expire_test")
        assert result is None


class TestPayPalAccessTokenAsync:
    """Tests para obtención de access token de PayPal."""

    def setup_method(self):
        _clear_token_cache()
        _reset_paypal_clients()

    @pytest.mark.asyncio
    async def test_returns_token_from_cache_if_available(self):
        """Devuelve token de cache si está disponible."""
        _set_cached_token("test_id:True", "cached_token", expires_in=3600)
        
        result = await _get_paypal_access_token_async(
            client_id="test_id",
            client_secret="test_secret",
            is_sandbox=True,
        )
        
        assert result == "cached_token"

    @pytest.mark.asyncio
    async def test_fetches_token_from_api_if_not_cached(self):
        """Obtiene token de API si no está en cache."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_token",
            "expires_in": 3600,
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch(
            "app.modules.payments.services.webhooks.signature_verification.get_paypal_token_client",
            return_value=mock_client
        ):
            result = await _get_paypal_access_token_async(
                client_id="fetch_test_id",
                client_secret="test_secret",
                is_sandbox=True,
            )

            assert result == "new_token"

    @pytest.mark.asyncio
    async def test_returns_none_on_non_200_response(self):
        """Devuelve None si la respuesta no es 200."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch(
            "app.modules.payments.services.webhooks.signature_verification.get_paypal_token_client",
            return_value=mock_client
        ):
            result = await _get_paypal_access_token_async(
                client_id="bad_id",
                client_secret="bad_secret",
                is_sandbox=True,
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_retries_on_transient_error_502(self):
        """Reintenta en error transitorio 502."""
        mock_response_502 = MagicMock()
        mock_response_502.status_code = 502
        mock_response_502.text = "Bad Gateway"

        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {
            "access_token": "retry_token",
            "expires_in": 3600,
        }

        mock_client = AsyncMock()
        # Primer intento: 502, segundo intento: 200
        mock_client.post = AsyncMock(side_effect=[mock_response_502, mock_response_200])

        with patch(
            "app.modules.payments.services.webhooks.signature_verification.get_paypal_token_client",
            return_value=mock_client
        ):
            with patch("asyncio.sleep", new=AsyncMock()):
                result = await _get_paypal_access_token_async(
                    client_id="retry_test_id",
                    client_secret="test_secret",
                    is_sandbox=True,
                )

            assert result == "retry_token"
            assert mock_client.post.call_count == 2


class TestPayPalVerifySignatureAsync:
    """Tests para verificación de firma PayPal."""

    def setup_method(self):
        _clear_token_cache()

    @pytest.mark.asyncio
    async def test_rejects_missing_required_headers(self):
        """Rechaza si faltan headers requeridos."""
        result = await verify_paypal_signature_via_api(
            payload=b'{"id": "evt_123"}',
            transmission_id="trans_id",
            transmission_sig=None,  # Faltante
            cert_url="https://cert.url",
            transmission_time="2025-01-01T00:00:00Z",
            auth_algo="SHA256withRSA",
            webhook_id="wh_123",
            client_id="client",
            client_secret="secret",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_rejects_missing_webhook_id(self):
        """Rechaza si falta webhook_id."""
        result = await verify_paypal_signature_via_api(
            payload=b'{"id": "evt_123"}',
            transmission_id="trans_id",
            transmission_sig="sig",
            cert_url="https://cert.url",
            transmission_time="2025-01-01T00:00:00Z",
            auth_algo="SHA256withRSA",
            webhook_id=None,  # Faltante
            client_id="client",
            client_secret="secret",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_rejects_missing_client_credentials(self):
        """Rechaza si faltan credenciales."""
        result = await verify_paypal_signature_via_api(
            payload=b'{"id": "evt_123"}',
            transmission_id="trans_id",
            transmission_sig="sig",
            cert_url="https://cert.url",
            transmission_time="2025-01-01T00:00:00Z",
            auth_algo="SHA256withRSA",
            webhook_id="wh_123",
            client_id=None,  # Faltante
            client_secret="secret",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_uses_explicit_timeouts(self):
        """Usa timeouts explícitos configurados."""
        # Este test verifica que httpx.AsyncClient se llama con el timeout correcto
        _set_cached_token("client:True", "test_token", expires_in=3600)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"verification_status": "SUCCESS"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            await verify_paypal_signature_via_api(
                payload=b'{"id": "evt_123"}',
                transmission_id="trans_id",
                transmission_sig="sig",
                cert_url="https://cert.url",
                transmission_time="2025-01-01T00:00:00Z",
                auth_algo="SHA256withRSA",
                webhook_id="wh_123",
                client_id="client",
                client_secret="secret",
            )

            # Verificar que se usó timeout explícito
            call_kwargs = mock_client_class.call_args
            assert call_kwargs is not None
            assert "timeout" in call_kwargs.kwargs


# Fin del archivo backend/tests/modules/payments/test_bloque_a_railway_readiness.py
