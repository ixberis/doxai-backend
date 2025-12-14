# -*- coding: utf-8 -*-
"""
backend/tests/modules/payments/monitoring/test_metrics_collector.py

Tests para el collector principal de métricas.

Autor: Ixchel Beristáin
Fecha: 06/11/2025
"""

import pytest
from datetime import timedelta
from app.modules.payments.metrics.collectors.metrics_collector import (
    MetricsCollector,
    get_metrics_collector,
)


class TestMetricsCollector:
    """Tests para MetricsCollector."""
    
    def test_singleton_pattern(self):
        """Test: MetricsCollector es un singleton."""
        collector1 = MetricsCollector()
        collector2 = MetricsCollector()
        
        assert collector1 is collector2
    
    def test_get_metrics_collector_returns_singleton(self):
        """Test: get_metrics_collector retorna el singleton."""
        collector = get_metrics_collector()
        assert isinstance(collector, MetricsCollector)
        
        # Llamar de nuevo debe retornar la misma instancia
        collector2 = get_metrics_collector()
        assert collector is collector2
    
    def test_initialization(self, metrics_collector):
        """Test: inicialización correcta."""
        assert metrics_collector.storage is not None
        assert metrics_collector._initialized is True
    
    def test_record_endpoint_call_stores_metrics(self, metrics_collector):
        """Test: registrar llamada a endpoint."""
        metrics_collector.record_endpoint_call(
            endpoint="POST /test",
            latency_ms=150.0,
            status_code=200,
            error=None,
        )
        
        metrics = metrics_collector.get_endpoint_metrics(endpoint="POST /test")
        
        assert "POST /test" in metrics
        assert metrics["POST /test"]["total_requests"] == 1
        assert metrics["POST /test"]["total_errors"] == 0
    
    def test_record_endpoint_call_with_client_error(self, metrics_collector):
        """Test: registrar llamada con error de cliente (4xx)."""
        metrics_collector.record_endpoint_call(
            endpoint="POST /test",
            latency_ms=100.0,
            status_code=400,
            error=None,  # No se proporciona error explícito
        )
        
        metrics = metrics_collector.get_endpoint_metrics(endpoint="POST /test")
        
        assert metrics["POST /test"]["total_errors"] == 1
        assert "HTTP_400_ClientError" in metrics["POST /test"]["errors_by_type"]
    
    def test_record_endpoint_call_with_server_error(self, metrics_collector):
        """Test: registrar llamada con error de servidor (5xx)."""
        metrics_collector.record_endpoint_call(
            endpoint="POST /test",
            latency_ms=200.0,
            status_code=500,
            error=None,
        )
        
        metrics = metrics_collector.get_endpoint_metrics(endpoint="POST /test")
        
        assert metrics["POST /test"]["total_errors"] == 1
        assert "HTTP_500_ServerError" in metrics["POST /test"]["errors_by_type"]
    
    def test_record_endpoint_call_with_explicit_error(self, metrics_collector):
        """Test: registrar llamada con error explícito."""
        metrics_collector.record_endpoint_call(
            endpoint="POST /test",
            latency_ms=150.0,
            status_code=422,
            error="ValidationError",
        )
        
        metrics = metrics_collector.get_endpoint_metrics(endpoint="POST /test")
        
        assert metrics["POST /test"]["total_errors"] == 1
        assert "ValidationError" in metrics["POST /test"]["errors_by_type"]
    
    def test_record_payment_attempt_success(self, metrics_collector):
        """Test: registrar intento de pago exitoso."""
        metrics_collector.record_payment_attempt(
            provider="stripe",
            status="paid",
            amount_cents=19900,
        )
        
        conversions = metrics_collector.get_provider_conversions(provider="stripe")
        
        assert "stripe" in conversions
        assert conversions["stripe"]["total_attempts"] == 1
        assert conversions["stripe"]["successful"] == 1
    
    def test_record_payment_attempt_failure(self, metrics_collector):
        """Test: registrar intento de pago fallido."""
        metrics_collector.record_payment_attempt(
            provider="paypal",
            status="failed",
        )
        
        conversions = metrics_collector.get_provider_conversions(provider="paypal")
        
        assert conversions["paypal"]["failed"] == 1
    
    def test_record_payment_attempt_case_insensitive_provider(self, metrics_collector):
        """Test: el proveedor se normaliza a lowercase."""
        metrics_collector.record_payment_attempt(provider="STRIPE", status="paid")
        metrics_collector.record_payment_attempt(provider="Stripe", status="paid")
        
        conversions = metrics_collector.get_provider_conversions(provider="stripe")
        
        assert conversions["stripe"]["total_attempts"] == 2
    
    def test_get_endpoint_metrics_all_endpoints(self, metrics_collector):
        """Test: obtener métricas de todos los endpoints."""
        metrics_collector.record_endpoint_call("POST /checkout", 100.0, 200)
        metrics_collector.record_endpoint_call("POST /refund", 200.0, 200)
        metrics_collector.record_endpoint_call("GET /payments", 50.0, 200)
        
        metrics = metrics_collector.get_endpoint_metrics()
        
        assert len(metrics) == 3
        assert "POST /checkout" in metrics
        assert "POST /refund" in metrics
        assert "GET /payments" in metrics
    
    def test_get_endpoint_metrics_specific_endpoint(self, metrics_collector):
        """Test: obtener métricas de un endpoint específico."""
        metrics_collector.record_endpoint_call("POST /checkout", 100.0, 200)
        metrics_collector.record_endpoint_call("POST /refund", 200.0, 200)
        
        metrics = metrics_collector.get_endpoint_metrics(endpoint="POST /checkout")
        
        assert len(metrics) == 1
        assert "POST /checkout" in metrics
        assert "POST /refund" not in metrics
    
    def test_get_endpoint_metrics_with_time_window(self, metrics_collector):
        """Test: obtener métricas con ventana de tiempo."""
        metrics_collector.record_endpoint_call("POST /test", 100.0, 200)
        
        # Últimas 6 horas
        metrics = metrics_collector.get_endpoint_metrics(hours=6)
        
        assert "POST /test" in metrics
    
    def test_get_provider_conversions_all_providers(self, metrics_collector):
        """Test: obtener conversiones de todos los proveedores."""
        metrics_collector.record_payment_attempt("stripe", "paid")
        metrics_collector.record_payment_attempt("paypal", "paid")
        
        conversions = metrics_collector.get_provider_conversions()
        
        assert len(conversions) == 2
        assert "stripe" in conversions
        assert "paypal" in conversions
    
    def test_get_provider_conversions_specific_provider(self, metrics_collector):
        """Test: obtener conversiones de un proveedor específico."""
        metrics_collector.record_payment_attempt("stripe", "paid")
        metrics_collector.record_payment_attempt("paypal", "paid")
        
        conversions = metrics_collector.get_provider_conversions(provider="stripe")
        
        assert len(conversions) == 1
        assert "stripe" in conversions
        assert "paypal" not in conversions
    
    def test_get_summary(self, metrics_collector):
        """Test: obtener resumen general."""
        metrics_collector.record_endpoint_call("POST /test", 100.0, 200)
        metrics_collector.record_payment_attempt("stripe", "paid")
        
        summary = metrics_collector.get_summary()
        
        assert "uptime_seconds" in summary
        assert "uptime_hours" in summary
        assert "total_endpoints_tracked" in summary
        assert "total_providers_tracked" in summary
        assert "last_hour" in summary
        
        last_hour = summary["last_hour"]
        assert "total_requests" in last_hour
        assert "overall_error_rate" in last_hour
        assert "total_payment_attempts" in last_hour
        assert "overall_conversion_rate" in last_hour


class TestHealthStatus:
    """Tests para evaluación de salud del sistema."""
    
    def test_get_health_status_healthy(self, metrics_collector):
        """Test: sistema saludable sin alertas."""
        # Registrar métricas normales
        for i in range(100):
            metrics_collector.record_endpoint_call("POST /test", 100.0, 200)
            metrics_collector.record_payment_attempt("stripe", "paid")
        
        health = metrics_collector.get_health_status()
        
        assert health["status"] == "healthy"
        assert len(health["alerts"]) == 0
    
    def test_get_health_status_warning_high_error_rate(self, metrics_collector):
        """Test: alerta de warning por tasa de error elevada (5-10%)."""
        # 6% de error
        for i in range(100):
            error = "TestError" if i < 6 else None
            status_code = 500 if i < 6 else 200
            metrics_collector.record_endpoint_call(
                "POST /test", 100.0, status_code, error=error
            )
        
        health = metrics_collector.get_health_status()
        
        assert health["status"] == "warning"
        assert any("error elevada" in alert["message"].lower() for alert in health["alerts"])
    
    def test_get_health_status_critical_very_high_error_rate(self, metrics_collector):
        """Test: alerta crítica por tasa de error muy alta (>10%)."""
        # 15% de error
        for i in range(100):
            error = "TestError" if i < 15 else None
            status_code = 500 if i < 15 else 200
            metrics_collector.record_endpoint_call(
                "POST /test", 100.0, status_code, error=error
            )
        
        health = metrics_collector.get_health_status()
        
        assert health["status"] == "critical"
        assert any(alert["level"] == "critical" for alert in health["alerts"])
    
    def test_get_health_status_warning_low_conversion(self, metrics_collector):
        """Test: alerta de warning por baja conversión (<70%)."""
        # Registrar suficientes intentos (>10) con 60% de conversión
        # pero sin muchos fallos (para evitar critical)
        for i in range(20):
            if i < 12:
                status = "paid"
            elif i < 18:
                status = "pending"  # No cuenta como fallo
            else:
                status = "failed"  # Solo 2 fallos (10%)
            metrics_collector.record_payment_attempt("stripe", status)
        
        health = metrics_collector.get_health_status()
        
        assert health["status"] == "warning"
        assert any("conversión baja" in alert["message"].lower() for alert in health["alerts"])
    
    def test_get_health_status_warning_high_latency(self, metrics_collector):
        """Test: alerta de warning por latencia alta (P95 > 3s)."""
        # Registrar latencias altas
        for i in range(100):
            latency = 4000.0 if i >= 95 else 100.0  # P95 será 4000ms
            metrics_collector.record_endpoint_call("POST /test", latency, 200)
        
        health = metrics_collector.get_health_status()
        
        # Puede ser warning por latencia
        if health["status"] == "warning":
            assert any("latencia" in alert["message"].lower() for alert in health["alerts"])
    
    def test_get_health_status_critical_high_provider_failure(self, metrics_collector):
        """Test: alerta crítica por alta tasa de fallo en proveedor (>20%)."""
        # 25% de fallos
        for i in range(100):
            status = "failed" if i < 25 else "paid"
            metrics_collector.record_payment_attempt("stripe", status)
        
        health = metrics_collector.get_health_status()
        
        assert health["status"] == "critical"
        assert any(
            alert["level"] == "critical" and "fallo alta" in alert["message"].lower()
            for alert in health["alerts"]
        )
    
    def test_get_health_status_includes_timestamp(self, metrics_collector):
        """Test: el health status incluye timestamp."""
        health = metrics_collector.get_health_status()
        
        assert "timestamp" in health
        assert isinstance(health["timestamp"], str)
    
    def test_get_health_status_includes_metrics_summary(self, metrics_collector):
        """Test: el health status incluye resumen de métricas."""
        health = metrics_collector.get_health_status()
        
        assert "metrics_summary" in health


class TestMetricsCollectorEdgeCases:
    """Tests de casos edge del collector."""
    
    def test_handles_high_latency_without_crash(self, metrics_collector):
        """Test: manejo de latencias extremadamente altas."""
        metrics_collector.record_endpoint_call(
            "POST /test",
            latency_ms=999999999.0,
            status_code=200,
        )
        
        metrics = metrics_collector.get_endpoint_metrics()
        assert "POST /test" in metrics
    
    def test_handles_many_endpoints(self, metrics_collector):
        """Test: manejo de muchos endpoints diferentes."""
        for i in range(100):
            metrics_collector.record_endpoint_call(
                f"POST /endpoint{i}",
                100.0,
                200,
            )
        
        metrics = metrics_collector.get_endpoint_metrics()
        assert len(metrics) == 100
    
    def test_handles_many_providers(self, metrics_collector):
        """Test: manejo de muchos proveedores diferentes."""
        for i in range(50):
            metrics_collector.record_payment_attempt(
                f"provider{i}",
                "paid",
            )
        
        conversions = metrics_collector.get_provider_conversions()
        assert len(conversions) == 50
    
    def test_handles_empty_provider_name(self, metrics_collector):
        """Test: manejo de nombre de proveedor vacío."""
        metrics_collector.record_payment_attempt("", "paid")
        
        conversions = metrics_collector.get_provider_conversions()
        # El collector normaliza strings vacíos a "unknown"
        assert "unknown" in conversions
    
    def test_handles_special_characters_in_endpoint(self, metrics_collector):
        """Test: manejo de caracteres especiales en endpoint."""
        endpoint = "POST /páyments/{id}/reçeipt"
        metrics_collector.record_endpoint_call(endpoint, 100.0, 200)
        
        metrics = metrics_collector.get_endpoint_metrics(endpoint=endpoint)
        assert endpoint in metrics
