# -*- coding: utf-8 -*-
"""
backend/tests/modules/payments/monitoring/test_metrics_storage.py

Tests para el almacenamiento y agregación de métricas.

Autor: Ixchel Beristáin
Fecha: 06/11/2025
"""

import pytest
from datetime import datetime, timedelta, timezone
from app.modules.payments.metrics.aggregators import (
    LatencyBucket,
    ConversionBucket,
    MetricsStorage,
    TimeWindow,
)


class TestLatencyBucket:
    """Tests para LatencyBucket."""
    
    def test_add_latency_increments_counter(self, latency_bucket):
        """Test: agregar latencia incrementa el contador."""
        latency_bucket.add_latency(100.0)
        assert latency_bucket.total_requests == 1
        assert len(latency_bucket.latencies) == 1
        assert latency_bucket.latencies[0] == 100.0
    
    def test_add_latency_with_error_increments_error_counter(self, latency_bucket):
        """Test: agregar latencia con error incrementa contadores de error."""
        latency_bucket.add_latency(200.0, error="ValidationError")
        
        assert latency_bucket.total_requests == 1
        assert latency_bucket.total_errors == 1
        assert latency_bucket.error_by_type["ValidationError"] == 1
    
    def test_get_percentiles_empty_bucket(self, latency_bucket):
        """Test: percentiles en bucket vacío retornan 0."""
        percentiles = latency_bucket.get_percentiles()
        
        assert percentiles["p50"] == 0.0
        assert percentiles["p95"] == 0.0
        assert percentiles["p99"] == 0.0
        # Nuevo campo agregado
        assert "avg" in percentiles
        assert percentiles["avg"] == 0.0
    
    def test_get_percentiles_calculates_correctly(self, latency_bucket, sample_latencies):
        """Test: cálculo correcto de percentiles."""
        for latency in sample_latencies:
            latency_bucket.add_latency(latency)
        
        percentiles = latency_bucket.get_percentiles()
        
        # Con 10 valores: [100, 120, 150, 180, 200, 250, 300, 400, 500, 1000]
        # Usando interpolación lineal:
        # p50 = valor en posición 4.5 → interpolación entre índices 4 y 5: 200 + 0.5*(250-200) = 225
        # p95 = valor en posición 8.55 → interpolación entre índices 8 y 9: 500 + 0.55*(1000-500) = 775
        # p99 = valor en posición 8.91 → interpolación entre índices 8 y 9: 500 + 0.91*(1000-500) = 955
        assert percentiles["p50"] == pytest.approx(225.0, abs=1)  # interpolación entre 200 y 250
        assert percentiles["p95"] == pytest.approx(775.0, abs=1)  # interpolación entre 500 y 1000
        assert percentiles["p99"] == pytest.approx(955.0, abs=1)  # interpolación entre 500 y 1000
        assert percentiles["avg"] == pytest.approx(320.0, rel=1e-2)
    
    def test_get_error_rate_no_requests(self, latency_bucket):
        """Test: tasa de error con 0 requests retorna 0."""
        assert latency_bucket.get_error_rate() == 0.0
    
    def test_get_error_rate_calculates_correctly(self, latency_bucket):
        """Test: cálculo correcto de tasa de error."""
        latency_bucket.add_latency(100.0)
        latency_bucket.add_latency(200.0, error="Error1")
        latency_bucket.add_latency(300.0)
        latency_bucket.add_latency(400.0, error="Error2")
        
        # 2 errores de 4 requests = 50%
        assert latency_bucket.get_error_rate() == 50.0
    
    def test_bucket_respects_maxlen(self):
        """Test: el bucket respeta el límite de 1000 latencias."""
        bucket = LatencyBucket()
        
        # Agregar más de 1000 latencias
        for i in range(1500):
            bucket.add_latency(float(i))
        
        # Solo debe mantener las últimas 1000
        assert len(bucket.latencies) == 1000
        assert bucket.total_requests == 1500  # El contador no se limita


class TestConversionBucket:
    """Tests para ConversionBucket."""
    
    def test_record_attempt_paid_status(self, conversion_bucket):
        """Test: registrar intento con status 'paid'."""
        conversion_bucket.record_attempt("paid")
        
        assert conversion_bucket.total_attempts == 1
        assert conversion_bucket.successful == 1
        assert conversion_bucket.failed == 0
    
    def test_record_attempt_failed_status(self, conversion_bucket):
        """Test: registrar intento con status 'failed'."""
        conversion_bucket.record_attempt("failed")
        
        assert conversion_bucket.total_attempts == 1
        assert conversion_bucket.successful == 0
        assert conversion_bucket.failed == 1
    
    def test_record_attempt_pending_status(self, conversion_bucket):
        """Test: registrar intento con status 'pending'."""
        conversion_bucket.record_attempt("pending")
        
        assert conversion_bucket.total_attempts == 1
        assert conversion_bucket.pending == 1
    
    def test_record_attempt_cancelled_status(self, conversion_bucket):
        """Test: registrar intento con status 'cancelled'."""
        conversion_bucket.record_attempt("cancelled")
        
        assert conversion_bucket.total_attempts == 1
        assert conversion_bucket.cancelled == 1
    
    def test_record_attempt_case_insensitive(self, conversion_bucket):
        """Test: los status son case-insensitive."""
        conversion_bucket.record_attempt("PAID")
        conversion_bucket.record_attempt("Failed")
        conversion_bucket.record_attempt("PENDING")
        
        assert conversion_bucket.successful == 1
        assert conversion_bucket.failed == 1
        assert conversion_bucket.pending == 1
    
    def test_get_conversion_rate_no_attempts(self, conversion_bucket):
        """Test: tasa de conversión con 0 intentos retorna 0."""
        assert conversion_bucket.conversion_rate() == 0.0
    
    def test_get_conversion_rate_calculates_correctly(self, conversion_bucket):
        """Test: cálculo correcto de tasa de conversión."""
        conversion_bucket.record_attempt("paid")
        conversion_bucket.record_attempt("paid")
        conversion_bucket.record_attempt("paid")
        conversion_bucket.record_attempt("failed")
        
        # 3 exitosos de 4 = 75%
        assert conversion_bucket.conversion_rate() == 75.0
    
    def test_get_failure_rate_calculates_correctly(self, conversion_bucket):
        """Test: cálculo correcto de tasa de fallo."""
        conversion_bucket.record_attempt("paid")
        conversion_bucket.record_attempt("failed")
        conversion_bucket.record_attempt("failed")
        conversion_bucket.record_attempt("pending")
        
        # 2 fallidos de 4 = 50%
        assert conversion_bucket.failure_rate() == 50.0


class TestMetricsStorage:
    """Tests para MetricsStorage."""
    
    def test_initialization(self, metrics_storage):
        """Test: inicialización correcta del storage."""
        assert metrics_storage.retention_hours == 24
        assert len(metrics_storage._endpoint_metrics) == 0
        assert len(metrics_storage._provider_conversions) == 0
        assert metrics_storage._start_time is not None
    
    def test_record_endpoint_call_stores_data(self, metrics_storage):
        """Test: registrar llamada a endpoint almacena los datos."""
        metrics_storage.record_endpoint_call(
            endpoint="POST /test",
            latency_ms=100.0,
            error=None,
        )
        
        assert "POST /test" in metrics_storage._endpoint_metrics
        assert len(metrics_storage._endpoint_metrics["POST /test"]) > 0
    
    def test_record_endpoint_call_with_error(self, metrics_storage):
        """Test: registrar llamada con error."""
        metrics_storage.record_endpoint_call(
            endpoint="POST /test",
            latency_ms=200.0,
            error="ValidationError",
        )
        
        endpoint_data = metrics_storage._endpoint_metrics["POST /test"]
        bucket = list(endpoint_data.values())[0]
        
        assert bucket.total_errors == 1
        assert bucket.error_by_type["ValidationError"] == 1
    
    def test_record_payment_attempt_stores_data(self, metrics_storage):
        """Test: registrar intento de pago almacena los datos."""
        metrics_storage.record_payment_attempt(
            provider="stripe",
            status="paid",
        )
        
        assert "stripe" in metrics_storage._provider_conversions
        assert len(metrics_storage._provider_conversions["stripe"]) > 0
    
    def test_get_window_timestamp_minute(self, metrics_storage):
        """Test: redondeo a ventana de minuto."""
        dt = datetime(2025, 11, 6, 12, 34, 56, 123456)
        result = metrics_storage._window_ts(dt, TimeWindow.MINUTE)
        
        assert result == datetime(2025, 11, 6, 12, 34, 0, 0)
    
    def test_get_window_timestamp_hour(self, metrics_storage):
        """Test: redondeo a ventana de hora."""
        dt = datetime(2025, 11, 6, 12, 34, 56)
        result = metrics_storage._window_ts(dt, TimeWindow.HOUR)
        
        assert result == datetime(2025, 11, 6, 12, 0, 0, 0)
    
    def test_get_window_timestamp_day(self, metrics_storage):
        """Test: redondeo a ventana de día."""
        dt = datetime(2025, 11, 6, 12, 34, 56)
        result = metrics_storage._window_ts(dt, TimeWindow.DAY)
        
        assert result == datetime(2025, 11, 6, 0, 0, 0, 0)
    
    def test_get_endpoint_metrics_returns_aggregated_data(self, metrics_storage):
        """Test: obtener métricas agregadas de endpoints."""
        # Registrar varias llamadas
        for i in range(10):
            metrics_storage.record_endpoint_call(
                endpoint="POST /test",
                latency_ms=100.0 + i * 10,
                error=None if i % 3 != 0 else "TestError",
            )
        
        metrics = metrics_storage.get_endpoint_metrics(endpoint="POST /test")
        
        assert "POST /test" in metrics
        data = metrics["POST /test"]
        
        assert data["total_requests"] == 10
        assert data["total_errors"] == 4  # i=0,3,6,9
        assert data["error_rate"] == 40.0
        assert "latency" in data
        assert "errors_by_type" in data
    
    def test_get_endpoint_metrics_filters_by_time(self, metrics_storage, monkeypatch):
        """Test: filtrado por ventana de tiempo."""
        # Mock datetime.utcnow para controlar el tiempo
        now = datetime(2025, 11, 6, 12, 0, 0)
        
        # Registrar métricas en diferentes momentos
        old_timestamp = now - timedelta(hours=2)
        recent_timestamp = now - timedelta(minutes=30)
        
        # Inyectar datos directamente para controlar timestamps
        metrics_storage._endpoint_metrics["POST /test"][old_timestamp] = LatencyBucket()
        metrics_storage._endpoint_metrics["POST /test"][old_timestamp].add_latency(100.0)
        
        metrics_storage._endpoint_metrics["POST /test"][recent_timestamp] = LatencyBucket()
        metrics_storage._endpoint_metrics["POST /test"][recent_timestamp].add_latency(200.0)
        
        # Consultar solo última hora
        since = now - timedelta(hours=1)
        metrics = metrics_storage.get_endpoint_metrics(endpoint="POST /test", since=since)
        
        # Solo debe incluir la métrica reciente
        assert metrics["POST /test"]["total_requests"] == 1
    
    def test_get_provider_conversions_returns_aggregated_data(self, metrics_storage):
        """Test: obtener conversiones agregadas por proveedor."""
        # Registrar varios intentos
        statuses = ["paid", "paid", "paid", "failed", "pending"]
        for status in statuses:
            metrics_storage.record_payment_attempt(provider="stripe", status=status)
        
        conversions = metrics_storage.get_provider_conversions(provider="stripe")
        
        assert "stripe" in conversions
        data = conversions["stripe"]
        
        assert data["total_attempts"] == 5
        assert data["successful"] == 3
        assert data["failed"] == 1
        assert data["pending"] == 1
        assert data["conversion_rate"] == 60.0
    
    def test_get_summary_returns_overview(self, metrics_storage):
        """Test: obtener resumen general."""
        # Registrar algunas métricas
        metrics_storage.record_endpoint_call("POST /test", 100.0)
        metrics_storage.record_payment_attempt("stripe", "paid")
        
        summary = metrics_storage.get_summary()
        
        assert "uptime_seconds" in summary
        assert "total_endpoints_tracked" in summary
        assert "total_providers_tracked" in summary
        assert "last_hour" in summary
    
    def test_cleanup_removes_old_data(self, metrics_storage):
        """Test: cleanup elimina datos antiguos."""
        now = datetime.now(timezone.utc)
        old_timestamp = now - timedelta(hours=25)  # Más allá del retention
        recent_timestamp = now - timedelta(minutes=30)
        
        # Inyectar datos antiguos y recientes
        metrics_storage._endpoint_metrics["POST /old"][old_timestamp] = LatencyBucket()
        metrics_storage._endpoint_metrics["POST /recent"][recent_timestamp] = LatencyBucket()
        
        # Forzar cleanup
        metrics_storage._cleanup_old_data()
        
        # Los datos antiguos deben haberse eliminado
        assert "POST /old" not in metrics_storage._endpoint_metrics
        assert "POST /recent" in metrics_storage._endpoint_metrics
    
    def test_thread_safety_concurrent_writes(self, metrics_storage):
        """Test: escrituras concurrentes son thread-safe."""
        import threading
        
        def write_metrics():
            for i in range(100):
                metrics_storage.record_endpoint_call(
                    endpoint="POST /concurrent",
                    latency_ms=float(i),
                )
        
        # Crear múltiples threads
        threads = [threading.Thread(target=write_metrics) for _ in range(5)]
        
        # Iniciar todos los threads
        for t in threads:
            t.start()
        
        # Esperar a que terminen
        for t in threads:
            t.join()
        
        # Verificar que se registraron todas las métricas
        metrics = metrics_storage.get_endpoint_metrics(endpoint="POST /concurrent")
        assert metrics["POST /concurrent"]["total_requests"] == 500


class TestMetricsStorageEdgeCases:
    """Tests de casos edge del storage."""
    
    def test_empty_storage_returns_empty_metrics(self, metrics_storage):
        """Test: storage vacío retorna métricas vacías."""
        metrics = metrics_storage.get_endpoint_metrics()
        assert metrics == {}
        
        conversions = metrics_storage.get_provider_conversions()
        assert conversions == {}
    
    def test_get_metrics_for_nonexistent_endpoint(self, metrics_storage):
        """Test: consultar endpoint inexistente retorna vacío."""
        metrics = metrics_storage.get_endpoint_metrics(endpoint="POST /nonexistent")
        assert metrics == {}
    
    def test_get_conversions_for_nonexistent_provider(self, metrics_storage):
        """Test: consultar proveedor inexistente retorna vacío."""
        conversions = metrics_storage.get_provider_conversions(provider="nonexistent")
        assert conversions == {}
    
    def test_handles_very_high_latencies(self, metrics_storage):
        """Test: manejo de latencias muy altas."""
        metrics_storage.record_endpoint_call("POST /slow", 999999.0)
        
        metrics = metrics_storage.get_endpoint_metrics(endpoint="POST /slow")
        assert metrics["POST /slow"]["latency"]["p99"] == 999999.0
    
    def test_handles_many_error_types(self, metrics_storage):
        """Test: manejo de muchos tipos de error diferentes."""
        for i in range(50):
            metrics_storage.record_endpoint_call(
                "POST /errors",
                100.0,
                error=f"Error{i}",
            )
        
        metrics = metrics_storage.get_endpoint_metrics(endpoint="POST /errors")
        assert len(metrics["POST /errors"]["errors_by_type"]) == 50
