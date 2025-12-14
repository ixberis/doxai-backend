# -*- coding: utf-8 -*-
"""
Tests FASE 0: Verificación de firmas de webhooks.

Estos tests validan que:
1. El bypass inseguro SOLO funciona en desarrollo
2. Se rechazan firmas inválidas en producción
3. PayPal usa verificación vía API oficial (async)
4. No se registran eventos con payment_id=0
5. Faltan headers requeridos → reject

Autor: DoxAI
Fecha: 2025-12-13
"""
import pytest
import os
import time
import hmac
import hashlib
import json
from unittest.mock import patch, MagicMock, AsyncMock


class TestStripeSignatureVerification:
    """Tests para verificación de firma Stripe."""
    
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        """Setup para cada test."""
        monkeypatch.delenv("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("PYTHON_ENV", raising=False)
        
    def test_rejects_missing_signature_in_production(self, monkeypatch):
        """Debe rechazar si falta el header de firma en producción."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", "false")
        
        from app.modules.payments.services.webhooks.signature_verification import (
            verify_stripe_signature,
            _allow_insecure,
        )
        
        assert _allow_insecure() is False
        
        payload = b'{"id": "evt_test", "type": "payment_intent.succeeded"}'
        
        result = verify_stripe_signature(
            payload=payload,
            signature_header=None,
            webhook_secret="whsec_test123",
        )
        
        assert result is False
    
    def test_rejects_invalid_signature_in_production(self, monkeypatch):
        """Debe rechazar firma inválida en producción."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", "false")
        
        from app.modules.payments.services.webhooks.signature_verification import (
            verify_stripe_signature,
        )
        
        payload = b'{"id": "evt_test", "type": "payment_intent.succeeded"}'
        timestamp = str(int(time.time()))
        
        bad_signature = "invalid_signature_here"
        signature_header = f"t={timestamp},v1={bad_signature}"
        
        result = verify_stripe_signature(
            payload=payload,
            signature_header=signature_header,
            webhook_secret="whsec_test123",
        )
        
        assert result is False
    
    def test_rejects_expired_timestamp(self, monkeypatch):
        """Debe rechazar si el timestamp es muy antiguo."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        
        from app.modules.payments.services.webhooks.signature_verification import (
            verify_stripe_signature,
        )
        
        payload = b'{"id": "evt_test", "type": "payment_intent.succeeded"}'
        webhook_secret = "whsec_test123"
        
        # Timestamp de hace 10 minutos
        old_timestamp = str(int(time.time()) - 600)
        
        signed_payload = f"{old_timestamp}.".encode() + payload
        signature = hmac.new(
            webhook_secret.encode(),
            msg=signed_payload,
            digestmod=hashlib.sha256
        ).hexdigest()
        
        signature_header = f"t={old_timestamp},v1={signature}"
        
        result = verify_stripe_signature(
            payload=payload,
            signature_header=signature_header,
            webhook_secret=webhook_secret,
            tolerance_seconds=300,
        )
        
        assert result is False
    
    def test_accepts_valid_signature(self, monkeypatch):
        """Debe aceptar firma válida dentro de tolerancia."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        
        from app.modules.payments.services.webhooks.signature_verification import (
            verify_stripe_signature,
        )
        
        payload = b'{"id": "evt_test", "type": "payment_intent.succeeded"}'
        webhook_secret = "whsec_test123"
        
        timestamp = str(int(time.time()))
        
        signed_payload = f"{timestamp}.".encode() + payload
        signature = hmac.new(
            webhook_secret.encode(),
            msg=signed_payload,
            digestmod=hashlib.sha256
        ).hexdigest()
        
        signature_header = f"t={timestamp},v1={signature}"
        
        result = verify_stripe_signature(
            payload=payload,
            signature_header=signature_header,
            webhook_secret=webhook_secret,
        )
        
        assert result is True
    
    def test_bypass_blocked_in_production_even_with_flag(self, monkeypatch):
        """En producción, PAYMENTS_ALLOW_INSECURE_WEBHOOKS=true NO debe funcionar."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", "true")
        
        from app.modules.payments.services.webhooks.signature_verification import (
            _allow_insecure,
        )
        
        # Debe ser False aunque el flag esté en true
        assert _allow_insecure() is False
    
    def test_bypass_works_in_development_with_flag(self, monkeypatch):
        """En desarrollo con flag=true, debe permitir bypass."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", "true")
        
        from app.modules.payments.services.webhooks.signature_verification import (
            verify_stripe_signature,
            _allow_insecure,
        )
        
        assert _allow_insecure() is True
        
        # Sin firma, debe pasar en desarrollo con bypass
        result = verify_stripe_signature(
            payload=b'{"test": true}',
            signature_header=None,
            webhook_secret="whsec_test",
        )
        
        assert result is True
    
    def test_bypass_disabled_in_development_without_flag(self, monkeypatch):
        """En desarrollo SIN flag, debe requerir verificación."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", "false")
        
        from app.modules.payments.services.webhooks.signature_verification import (
            verify_stripe_signature,
            _allow_insecure,
        )
        
        assert _allow_insecure() is False


class TestPayPalSignatureVerification:
    """Tests para verificación de firma PayPal vía API (async)."""
    
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        """Setup para cada test."""
        monkeypatch.delenv("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
    
    @pytest.mark.asyncio
    async def test_rejects_missing_transmission_id(self, monkeypatch):
        """Debe rechazar si falta PAYPAL-TRANSMISSION-ID."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        
        from app.modules.payments.services.webhooks.signature_verification import (
            verify_paypal_signature_via_api,
        )
        
        payload = b'{"id": "WH-123", "event_type": "PAYMENT.CAPTURE.COMPLETED"}'
        
        result = await verify_paypal_signature_via_api(
            payload=payload,
            transmission_id=None,  # FALTA
            transmission_sig="some_sig",
            cert_url="https://cert.paypal.com",
            transmission_time="2025-01-01T00:00:00Z",
            auth_algo="SHA256withRSA",
            webhook_id="WH-ID-123",
            client_id="test_client",
            client_secret="test_secret",
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_rejects_missing_transmission_sig(self, monkeypatch):
        """Debe rechazar si falta PAYPAL-TRANSMISSION-SIG."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        
        from app.modules.payments.services.webhooks.signature_verification import (
            verify_paypal_signature_via_api,
        )
        
        payload = b'{"id": "WH-123", "event_type": "PAYMENT.CAPTURE.COMPLETED"}'
        
        result = await verify_paypal_signature_via_api(
            payload=payload,
            transmission_id="TX-123",
            transmission_sig=None,  # FALTA
            cert_url="https://cert.paypal.com",
            transmission_time="2025-01-01T00:00:00Z",
            auth_algo="SHA256withRSA",
            webhook_id="WH-ID-123",
            client_id="test_client",
            client_secret="test_secret",
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_rejects_missing_cert_url(self, monkeypatch):
        """Debe rechazar si falta PAYPAL-CERT-URL (fail-closed)."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        
        from app.modules.payments.services.webhooks.signature_verification import (
            verify_paypal_signature_via_api,
        )
        
        payload = b'{"id": "WH-123", "event_type": "PAYMENT.CAPTURE.COMPLETED"}'
        
        result = await verify_paypal_signature_via_api(
            payload=payload,
            transmission_id="TX-123",
            transmission_sig="some_sig",
            cert_url=None,  # FALTA - debe rechazar
            transmission_time="2025-01-01T00:00:00Z",
            auth_algo="SHA256withRSA",
            webhook_id="WH-ID-123",
            client_id="test_client",
            client_secret="test_secret",
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_rejects_missing_auth_algo(self, monkeypatch):
        """Debe rechazar si falta PAYPAL-AUTH-ALGO (fail-closed)."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        
        from app.modules.payments.services.webhooks.signature_verification import (
            verify_paypal_signature_via_api,
        )
        
        payload = b'{"id": "WH-123", "event_type": "PAYMENT.CAPTURE.COMPLETED"}'
        
        result = await verify_paypal_signature_via_api(
            payload=payload,
            transmission_id="TX-123",
            transmission_sig="some_sig",
            cert_url="https://cert.paypal.com",
            transmission_time="2025-01-01T00:00:00Z",
            auth_algo=None,  # FALTA - debe rechazar
            webhook_id="WH-ID-123",
            client_id="test_client",
            client_secret="test_secret",
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_rejects_missing_webhook_id(self, monkeypatch):
        """Debe rechazar si falta webhook_id."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        
        from app.modules.payments.services.webhooks.signature_verification import (
            verify_paypal_signature_via_api,
        )
        
        payload = b'{"id": "WH-123", "event_type": "PAYMENT.CAPTURE.COMPLETED"}'
        
        result = await verify_paypal_signature_via_api(
            payload=payload,
            transmission_id="TX-123",
            transmission_sig="some_sig",
            cert_url="https://cert.paypal.com",
            transmission_time="2025-01-01T00:00:00Z",
            auth_algo="SHA256withRSA",
            webhook_id=None,  # FALTA
            client_id="test_client",
            client_secret="test_secret",
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_rejects_missing_client_credentials(self, monkeypatch):
        """Debe rechazar si faltan client_id o client_secret."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        
        from app.modules.payments.services.webhooks.signature_verification import (
            verify_paypal_signature_via_api,
        )
        
        payload = b'{"id": "WH-123", "event_type": "PAYMENT.CAPTURE.COMPLETED"}'
        
        # Sin client_id
        result = await verify_paypal_signature_via_api(
            payload=payload,
            transmission_id="TX-123",
            transmission_sig="some_sig",
            cert_url="https://cert.paypal.com",
            transmission_time="2025-01-01T00:00:00Z",
            auth_algo="SHA256withRSA",
            webhook_id="WH-ID-123",
            client_id=None,
            client_secret="test_secret",
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_rejects_when_paypal_api_returns_failure(self, monkeypatch):
        """Debe rechazar cuando PayPal API devuelve verification_status != SUCCESS."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        
        from app.modules.payments.services.webhooks.signature_verification import (
            verify_paypal_signature_via_api,
            _paypal_token_cache,
        )
        
        # Limpiar cache
        _paypal_token_cache.clear()
        
        # Mock httpx.AsyncClient
        mock_response_token = MagicMock()
        mock_response_token.status_code = 200
        mock_response_token.json.return_value = {"access_token": "test_token", "expires_in": 3600}
        
        mock_response_verify = MagicMock()
        mock_response_verify.status_code = 200
        mock_response_verify.json.return_value = {"verification_status": "FAILURE"}
        
        async def mock_post(url, **kwargs):
            if "oauth2/token" in url:
                return mock_response_token
            return mock_response_verify
        
        mock_client = MagicMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        
        with patch("app.modules.payments.services.webhooks.signature_verification.httpx.AsyncClient", return_value=mock_client):
            payload = b'{"id": "WH-123", "event_type": "PAYMENT.CAPTURE.COMPLETED"}'
            
            result = await verify_paypal_signature_via_api(
                payload=payload,
                transmission_id="TX-123",
                transmission_sig="some_sig",
                cert_url="https://cert.paypal.com",
                transmission_time="2025-01-01T00:00:00Z",
                auth_algo="SHA256withRSA",
                webhook_id="WH-ID-123",
                client_id="test_client",
                client_secret="test_secret",
            )
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_accepts_when_paypal_api_returns_success(self, monkeypatch):
        """Debe aceptar cuando PayPal API devuelve verification_status == SUCCESS."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("PYTHON_ENV", "production")
        
        from app.modules.payments.services.webhooks.signature_verification import (
            verify_paypal_signature_via_api,
            _paypal_token_cache,
        )
        
        # Limpiar cache
        _paypal_token_cache.clear()
        
        # Mock response para token
        mock_response_token = MagicMock()
        mock_response_token.status_code = 200
        mock_response_token.json.return_value = {"access_token": "test_token", "expires_in": 3600}
        
        # Mock response para verify
        mock_response_verify = MagicMock()
        mock_response_verify.status_code = 200
        mock_response_verify.json.return_value = {"verification_status": "SUCCESS"}
        
        # Mock client que devuelve respuestas según URL
        async def mock_post_token(url, **kwargs):
            return mock_response_token
        
        async def mock_post_verify(url, **kwargs):
            return mock_response_verify
        
        mock_token_client = MagicMock()
        mock_token_client.post = mock_post_token
        
        mock_verify_client = MagicMock()
        mock_verify_client.post = mock_post_verify
        
        # Mockear los getters de clientes singleton
        monkeypatch.setattr(
            "app.modules.payments.services.webhooks.signature_verification.get_paypal_token_client",
            lambda: mock_token_client,
        )
        monkeypatch.setattr(
            "app.modules.payments.services.webhooks.signature_verification.get_paypal_verify_client",
            lambda: mock_verify_client,
        )
        
        payload = b'{"id": "WH-123", "event_type": "PAYMENT.CAPTURE.COMPLETED"}'
        
        result = await verify_paypal_signature_via_api(
            payload=payload,
            transmission_id="TX-123",
            transmission_sig="some_sig",
            cert_url="https://cert.paypal.com",
            transmission_time="2025-01-01T00:00:00Z",
            auth_algo="SHA256withRSA",
            webhook_id="WH-ID-123",
            client_id="test_client",
            client_secret="test_secret",
        )
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_rejects_when_token_request_fails(self, monkeypatch):
        """Debe rechazar si no puede obtener access token."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        
        from app.modules.payments.services.webhooks.signature_verification import (
            verify_paypal_signature_via_api,
            _paypal_token_cache,
        )
        
        # Limpiar cache
        _paypal_token_cache.clear()
        
        # Mock httpx.AsyncClient - token fails
        mock_response_token = MagicMock()
        mock_response_token.status_code = 401
        mock_response_token.text = "Unauthorized"
        
        async def mock_post(url, **kwargs):
            return mock_response_token
        
        mock_client = MagicMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        
        with patch("app.modules.payments.services.webhooks.signature_verification.httpx.AsyncClient", return_value=mock_client):
            payload = b'{"id": "WH-123", "event_type": "PAYMENT.CAPTURE.COMPLETED"}'
            
            result = await verify_paypal_signature_via_api(
                payload=payload,
                transmission_id="TX-123",
                transmission_sig="some_sig",
                cert_url="https://cert.paypal.com",
                transmission_time="2025-01-01T00:00:00Z",
                auth_algo="SHA256withRSA",
                webhook_id="WH-ID-123",
                client_id="test_client",
                client_secret="test_secret",
            )
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_token_cache_works(self, monkeypatch):
        """Debe cachear el token y no pedir uno nuevo en cada llamada."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("PYTHON_ENV", "production")
        
        from app.modules.payments.services.webhooks.signature_verification import (
            _get_paypal_access_token_async,
            _paypal_token_cache,
        )
        
        # Limpiar cache
        _paypal_token_cache.clear()
        
        call_count = 0
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "cached_token", "expires_in": 3600}
        
        async def mock_post(url, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_response
        
        mock_client = MagicMock()
        mock_client.post = mock_post
        
        # Mockear el getter de cliente singleton
        monkeypatch.setattr(
            "app.modules.payments.services.webhooks.signature_verification.get_paypal_token_client",
            lambda: mock_client,
        )
        
        # Primera llamada - debe llamar a API
        token1 = await _get_paypal_access_token_async("client", "secret", True)
        assert token1 == "cached_token"
        assert call_count == 1
        
        # Segunda llamada - debe usar cache
        token2 = await _get_paypal_access_token_async("client", "secret", True)
        assert token2 == "cached_token"
        assert call_count == 1  # No debe haber llamado de nuevo


class TestWebhookNormalization:
    """Tests para normalización de webhooks."""
    
    def test_rejects_invalid_json(self):
        """Debe rechazar JSON inválido."""
        from app.modules.payments.facades.webhooks.normalize import (
            normalize_webhook_payload,
            WebhookNormalizationError,
        )
        from app.modules.payments.enums import PaymentProvider
        
        with pytest.raises(WebhookNormalizationError):
            normalize_webhook_payload(
                provider=PaymentProvider.STRIPE,
                raw_body=b"not valid json",
                headers={},
            )
    
    def test_rejects_stripe_missing_type(self):
        """Debe rechazar evento Stripe sin 'type'."""
        from app.modules.payments.facades.webhooks.normalize import (
            normalize_webhook_payload,
            WebhookNormalizationError,
        )
        from app.modules.payments.enums import PaymentProvider
        
        payload = json.dumps({"id": "evt_123"}).encode()
        
        with pytest.raises(WebhookNormalizationError, match="missing 'type'"):
            normalize_webhook_payload(
                provider=PaymentProvider.STRIPE,
                raw_body=payload,
                headers={},
            )
    
    def test_rejects_paypal_missing_event_type(self):
        """Debe rechazar evento PayPal sin 'event_type'."""
        from app.modules.payments.facades.webhooks.normalize import (
            normalize_webhook_payload,
            WebhookNormalizationError,
        )
        from app.modules.payments.enums import PaymentProvider
        
        payload = json.dumps({"id": "WH-123"}).encode()
        
        with pytest.raises(WebhookNormalizationError, match="missing 'event_type'"):
            normalize_webhook_payload(
                provider=PaymentProvider.PAYPAL,
                raw_body=payload,
                headers={},
            )
    
    def test_normalizes_stripe_checkout_completed(self):
        """Debe normalizar correctamente checkout.session.completed."""
        from app.modules.payments.facades.webhooks.normalize import (
            normalize_webhook_payload,
        )
        from app.modules.payments.enums import PaymentProvider
        
        payload = json.dumps({
            "id": "evt_123",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_123",
                    "payment_intent": "pi_123",
                    "amount_total": 5000,
                    "currency": "usd",
                    "customer": "cus_123",
                    "metadata": {"payment_id": "42"},
                }
            }
        }).encode()
        
        result = normalize_webhook_payload(
            provider=PaymentProvider.STRIPE,
            raw_body=payload,
            headers={},
        )
        
        assert result.event_id == "evt_123"
        assert result.event_type == "checkout.session.completed"
        assert result.provider_session_id == "cs_123"
        assert result.provider_payment_id == "pi_123"
        assert result.amount_cents == 5000
        assert result.currency == "USD"
        assert result.payment_id == 42
        assert result.is_success is True
        assert result.is_failure is False


class TestWebhookHandlerPaymentIdValidation:
    """Tests para validar que NO se registran eventos con payment_id=0."""
    
    @pytest.mark.asyncio
    async def test_handler_ignores_event_without_payment_id(self, monkeypatch):
        """Handler debe ignorar eventos sin payment_id, no llamar register_event con 0."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", "true")
        
        from app.modules.payments.facades.payments.webhook_handler import handle_webhook
        from app.modules.payments.enums import PaymentProvider
        
        # Mocks
        mock_session = MagicMock()
        mock_payment_service = MagicMock()
        mock_payment_repo = MagicMock()
        mock_payment_repo.get_by_provider_payment_id = AsyncMock(return_value=None)
        mock_refund_service = MagicMock()
        mock_refund_repo = MagicMock()
        mock_event_service = MagicMock()
        mock_event_service.register_event = AsyncMock()
        
        # Payload SIN payment_id en metadata
        payload = json.dumps({
            "id": "evt_test",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_123",
                    "payment_intent": "pi_123",
                    "amount_total": 5000,
                    "currency": "usd",
                    "metadata": {},  # SIN payment_id
                }
            }
        }).encode()
        
        result = await handle_webhook(
            session=mock_session,
            provider=PaymentProvider.STRIPE,
            raw_body=payload,
            headers={},
            payment_service=mock_payment_service,
            payment_repo=mock_payment_repo,
            refund_service=mock_refund_service,
            refund_repo=mock_refund_repo,
            event_service=mock_event_service,
        )
        
        # Debe ignorar el evento
        assert result["status"] == "ignored"
        assert "payment_id not found" in result["reason"]
        
        # NO debe haber llamado a register_event
        mock_event_service.register_event.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_handler_processes_event_with_valid_payment_id(self, monkeypatch):
        """Handler debe procesar eventos con payment_id válido."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", "true")
        
        from app.modules.payments.facades.payments.webhook_handler import handle_webhook
        from app.modules.payments.enums import PaymentProvider
        
        # Mock payment
        mock_payment = MagicMock()
        mock_payment.id = 42
        mock_payment.credits_awarded = 100
        
        # Mocks
        mock_session = MagicMock()
        mock_payment_service = MagicMock()
        mock_payment_repo = MagicMock()
        mock_payment_repo.get_by_provider_payment_id = AsyncMock(return_value=None)
        mock_refund_service = MagicMock()
        mock_refund_repo = MagicMock()
        mock_event_service = MagicMock()
        mock_event_service.register_event = AsyncMock(return_value=MagicMock(_was_existing=False))
        
        # Mock handle_payment_success
        with patch(
            "app.modules.payments.facades.payments.webhook_handler.handle_payment_success",
            new=AsyncMock(return_value=mock_payment)
        ):
            # Payload CON payment_id
            payload = json.dumps({
                "id": "evt_test",
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": "cs_123",
                        "payment_intent": "pi_123",
                        "amount_total": 5000,
                        "currency": "usd",
                        "metadata": {"payment_id": "42"},  # CON payment_id
                    }
                }
            }).encode()
            
            result = await handle_webhook(
                session=mock_session,
                provider=PaymentProvider.STRIPE,
                raw_body=payload,
                headers={},
                payment_service=mock_payment_service,
                payment_repo=mock_payment_repo,
                refund_service=mock_refund_service,
                refund_repo=mock_refund_repo,
                event_service=mock_event_service,
            )
            
            # Debe procesar exitosamente
            assert result["status"] == "ok"
            assert result["payment_id"] == 42
            
            # Debe haber llamado a register_event con payment_id válido
            mock_event_service.register_event.assert_called_once()
            call_args = mock_event_service.register_event.call_args
            assert call_args.kwargs.get("payment_id") == 42
    
    @pytest.mark.asyncio
    async def test_handler_rejects_invalid_signature_in_production(self, monkeypatch):
        """Handler debe rechazar webhook con firma inválida en producción."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", "false")
        
        from app.modules.payments.facades.payments.webhook_handler import (
            handle_webhook,
            WebhookSignatureError,
        )
        from app.modules.payments.enums import PaymentProvider
        
        mock_session = MagicMock()
        
        payload = json.dumps({
            "id": "evt_123",
            "type": "payment_intent.succeeded",
            "data": {"object": {}}
        }).encode()
        
        with pytest.raises(WebhookSignatureError):
            await handle_webhook(
                session=mock_session,
                provider=PaymentProvider.STRIPE,
                raw_body=payload,
                headers={},  # Sin header de firma
                payment_service=MagicMock(),
                payment_repo=MagicMock(),
                refund_service=MagicMock(),
                refund_repo=MagicMock(),
                event_service=MagicMock(),
            )
