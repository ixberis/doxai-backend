# -*- coding: utf-8 -*-
"""
backend/tests/modules/payments/monitoring/test_decorators.py

Tests para decorators de captura automática de métricas.

Autor: Ixchel Beristáin
Fecha: 06/11/2025
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from fastapi import HTTPException, Request

from app.modules.payments.metrics.collectors.decorators import (
    track_endpoint_metrics,
    track_payment_conversion,
    track_method_metrics,
)
from app.modules.payments.metrics.collectors.metrics_collector import get_metrics_collector


@pytest.fixture
def mock_request():
    """Mock de FastAPI Request."""
    request = Mock(spec=Request)
    request.headers = {"user-agent": "TestAgent/1.0"}
    request.client = Mock()
    request.client.host = "127.0.0.1"
    return request


class TestTrackEndpointMetrics:
    """Tests para decorator track_endpoint_metrics."""
    
    @pytest.mark.asyncio
    async def test_decorator_tracks_successful_call(self, metrics_collector):
        """Test: decorator captura llamada exitosa."""
        
        @track_endpoint_metrics("POST /test")
        async def test_endpoint():
            return {"status": "ok"}
        
        result = await test_endpoint()
        
        assert result == {"status": "ok"}
        
        metrics = metrics_collector.get_endpoint_metrics(endpoint="POST /test")
        assert "POST /test" in metrics
        assert metrics["POST /test"]["total_requests"] == 1
        assert metrics["POST /test"]["total_errors"] == 0
    
    @pytest.mark.asyncio
    async def test_decorator_tracks_latency(self, metrics_collector):
        """Test: decorator mide latencia correctamente."""
        import asyncio
        
        @track_endpoint_metrics("POST /slow")
        async def slow_endpoint():
            await asyncio.sleep(0.1)  # 100ms
            return {"status": "ok"}
        
        await slow_endpoint()
        
        metrics = metrics_collector.get_endpoint_metrics(endpoint="POST /slow")
        latency = metrics["POST /slow"]["latency"]["avg"]
        
        # Debe ser ~100ms (con margen amplio para overhead del sistema)
        assert 80 < latency < 250
    
    @pytest.mark.asyncio
    async def test_decorator_tracks_exception(self, metrics_collector):
        """Test: decorator captura excepciones."""
        
        @track_endpoint_metrics("POST /error")
        async def error_endpoint():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            await error_endpoint()
        
        metrics = metrics_collector.get_endpoint_metrics(endpoint="POST /error")
        assert metrics["POST /error"]["total_errors"] == 1
        assert "ValueError" in metrics["POST /error"]["errors_by_type"]
    
    @pytest.mark.asyncio
    async def test_decorator_tracks_http_exception(self, metrics_collector):
        """Test: decorator captura HTTPException con status code."""
        
        @track_endpoint_metrics("POST /forbidden")
        async def forbidden_endpoint():
            raise HTTPException(status_code=403, detail="Forbidden")
        
        with pytest.raises(HTTPException):
            await forbidden_endpoint()
        
        metrics = metrics_collector.get_endpoint_metrics(endpoint="POST /forbidden")
        assert metrics["POST /forbidden"]["total_errors"] == 1
    
    @pytest.mark.asyncio
    async def test_decorator_with_request_parameter(self, metrics_collector, mock_request):
        """Test: decorator funciona con parámetro Request."""
        
        @track_endpoint_metrics("POST /with-request")
        async def endpoint_with_request(request: Request):
            return {"client": request.client.host}
        
        result = await endpoint_with_request(mock_request)
        
        assert result["client"] == "127.0.0.1"
        
        metrics = metrics_collector.get_endpoint_metrics(endpoint="POST /with-request")
        assert "POST /with-request" in metrics
    
    @pytest.mark.asyncio
    async def test_decorator_uses_default_name_if_not_provided(self, metrics_collector):
        """Test: decorator usa nombre por defecto si no se proporciona."""
        
        @track_endpoint_metrics()
        async def my_endpoint():
            return {"status": "ok"}
        
        await my_endpoint()
        
        # El nombre por defecto incluye el módulo y nombre de función
        metrics = metrics_collector.get_endpoint_metrics()
        assert any("my_endpoint" in key for key in metrics.keys())
    
    def test_decorator_on_sync_function(self, metrics_collector):
        """Test: decorator funciona en funciones síncronas."""
        
        @track_endpoint_metrics("GET /sync")
        def sync_endpoint():
            return {"status": "ok"}
        
        result = sync_endpoint()
        
        assert result == {"status": "ok"}
        
        metrics = metrics_collector.get_endpoint_metrics(endpoint="GET /sync")
        assert "GET /sync" in metrics
    
    def test_decorator_on_sync_function_with_error(self, metrics_collector):
        """Test: decorator captura errores en funciones síncronas."""
        
        @track_endpoint_metrics("GET /sync-error")
        def sync_error_endpoint():
            raise RuntimeError("Sync error")
        
        with pytest.raises(RuntimeError):
            sync_error_endpoint()
        
        metrics = metrics_collector.get_endpoint_metrics(endpoint="GET /sync-error")
        assert metrics["GET /sync-error"]["total_errors"] == 1


class TestTrackPaymentConversion:
    """Tests para decorator track_payment_conversion."""
    
    @pytest.mark.asyncio
    async def test_decorator_tracks_successful_payment(self, metrics_collector):
        """Test: decorator registra pago exitoso."""
        
        @track_payment_conversion(provider_param="provider")
        async def process_payment(provider: str, amount: int):
            return {"status": "paid", "amount": amount}
        
        result = await process_payment(provider="stripe", amount=19900)
        
        assert result["status"] == "paid"
        
        conversions = metrics_collector.get_provider_conversions(provider="stripe")
        assert conversions["stripe"]["total_attempts"] == 1
        assert conversions["stripe"]["successful"] == 1
    
    @pytest.mark.asyncio
    async def test_decorator_tracks_failed_payment(self, metrics_collector):
        """Test: decorator registra pago fallido."""
        
        @track_payment_conversion(provider_param="provider")
        async def process_payment(provider: str):
            raise Exception("Payment failed")
        
        with pytest.raises(Exception):
            await process_payment(provider="paypal")
        
        conversions = metrics_collector.get_provider_conversions(provider="paypal")
        assert conversions["paypal"]["total_attempts"] == 1
        assert conversions["paypal"]["failed"] == 1
    
    @pytest.mark.asyncio
    async def test_decorator_extracts_status_from_result(self, metrics_collector):
        """Test: decorator extrae el status del resultado."""
        
        @track_payment_conversion(provider_param="provider")
        async def process_payment(provider: str):
            return {"payment_status": "pending", "provider": provider}
        
        await process_payment(provider="stripe")
        
        conversions = metrics_collector.get_provider_conversions(provider="stripe")
        assert conversions["stripe"]["pending"] == 1
    
    @pytest.mark.asyncio
    async def test_decorator_with_different_provider_param_name(self, metrics_collector):
        """Test: decorator con nombre de parámetro personalizado."""
        
        @track_payment_conversion(provider_param="payment_provider")
        async def process_payment(payment_provider: str, amount: int):
            return {"status": "paid"}
        
        await process_payment(payment_provider="paypal", amount=5000)
        
        conversions = metrics_collector.get_provider_conversions(provider="paypal")
        assert conversions["paypal"]["successful"] == 1
    
    @pytest.mark.asyncio
    async def test_decorator_handles_missing_provider(self, metrics_collector):
        """Test: decorator maneja proveedor faltante."""
        
        @track_payment_conversion(provider_param="provider")
        async def process_payment(other_param: str):
            return {"status": "paid"}
        
        await process_payment(other_param="test")
        
        conversions = metrics_collector.get_provider_conversions(provider="unknown")
        assert conversions["unknown"]["successful"] == 1
    
    def test_decorator_on_sync_function(self, metrics_collector):
        """Test: decorator funciona en funciones síncronas."""
        
        @track_payment_conversion(provider_param="provider")
        def sync_payment(provider: str):
            return {"status": "paid"}
        
        sync_payment(provider="stripe")
        
        conversions = metrics_collector.get_provider_conversions(provider="stripe")
        assert conversions["stripe"]["successful"] == 1


class TestTrackMethodMetrics:
    """Tests para decorator track_method_metrics."""
    
    @pytest.mark.asyncio
    async def test_decorator_tracks_service_method(self, metrics_collector):
        """Test: decorator rastrea método de servicio."""
        
        @track_method_metrics("PaymentService.create_payment")
        async def create_payment(amount: int):
            return {"id": 123, "amount": amount}
        
        result = await create_payment(amount=19900)
        
        assert result["id"] == 123
        
        metrics = metrics_collector.get_endpoint_metrics(
            endpoint="SERVICE:PaymentService.create_payment"
        )
        assert "SERVICE:PaymentService.create_payment" in metrics
    
    @pytest.mark.asyncio
    async def test_decorator_tracks_method_error(self, metrics_collector):
        """Test: decorator captura errores en métodos."""
        
        @track_method_metrics("CreditService.reserve")
        async def reserve_credits():
            raise ValueError("Insufficient balance")
        
        with pytest.raises(ValueError):
            await reserve_credits()
        
        metrics = metrics_collector.get_endpoint_metrics(
            endpoint="SERVICE:CreditService.reserve"
        )
        assert metrics["SERVICE:CreditService.reserve"]["total_errors"] == 1


class TestDecoratorsCombined:
    """Tests de uso combinado de decorators."""
    
    @pytest.mark.asyncio
    async def test_combined_decorators(self, metrics_collector):
        """Test: uso combinado de ambos decorators."""
        
        @track_endpoint_metrics("POST /checkout")
        @track_payment_conversion(provider_param="provider")
        async def checkout_endpoint(provider: str, amount: int):
            return {"status": "paid", "provider": provider, "amount": amount}
        
        result = await checkout_endpoint(provider="stripe", amount=19900)
        
        # Verificar métricas de endpoint
        endpoint_metrics = metrics_collector.get_endpoint_metrics(
            endpoint="POST /checkout"
        )
        assert "POST /checkout" in endpoint_metrics
        
        # Verificar métricas de conversión
        conversions = metrics_collector.get_provider_conversions(provider="stripe")
        assert conversions["stripe"]["successful"] == 1
    
    @pytest.mark.asyncio
    async def test_combined_decorators_with_error(self, metrics_collector):
        """Test: decorators combinados capturan errores correctamente."""
        
        @track_endpoint_metrics("POST /checkout")
        @track_payment_conversion(provider_param="provider")
        async def checkout_endpoint(provider: str):
            raise HTTPException(status_code=400, detail="Invalid payment")
        
        with pytest.raises(HTTPException):
            await checkout_endpoint(provider="paypal")
        
        # Ambos decorators deben registrar el error
        endpoint_metrics = metrics_collector.get_endpoint_metrics(
            endpoint="POST /checkout"
        )
        assert endpoint_metrics["POST /checkout"]["total_errors"] == 1
        
        conversions = metrics_collector.get_provider_conversions(provider="paypal")
        assert conversions["paypal"]["failed"] == 1


class TestDecoratorsEdgeCases:
    """Tests de casos edge de los decorators."""
    
    @pytest.mark.asyncio
    async def test_decorator_preserves_function_metadata(self, metrics_collector):
        """Test: decorator preserva metadata de la función."""
        
        @track_endpoint_metrics("POST /test")
        async def documented_endpoint():
            """This is a documented endpoint."""
            return {"status": "ok"}
        
        assert documented_endpoint.__name__ == "documented_endpoint"
        assert "documented endpoint" in documented_endpoint.__doc__
    
    @pytest.mark.asyncio
    async def test_decorator_handles_none_return(self, metrics_collector):
        """Test: decorator maneja retorno None."""
        
        @track_endpoint_metrics("POST /void")
        async def void_endpoint():
            return None
        
        result = await void_endpoint()
        assert result is None
        
        metrics = metrics_collector.get_endpoint_metrics(endpoint="POST /void")
        assert "POST /void" in metrics
    
    @pytest.mark.asyncio
    async def test_decorator_handles_complex_return_types(self, metrics_collector):
        """Test: decorator maneja tipos de retorno complejos."""
        
        @track_endpoint_metrics("POST /complex")
        async def complex_endpoint():
            return [{"id": 1}, {"id": 2}]
        
        result = await complex_endpoint()
        assert len(result) == 2
        
        metrics = metrics_collector.get_endpoint_metrics(endpoint="POST /complex")
        assert "POST /complex" in metrics
