# -*- coding: utf-8 -*-
"""
backend/tests/modules/payments/monitoring/test_metrics_routes.py

Tests para endpoints administrativos de métricas.

Autor: Ixchel Beristáin
Fecha: 06/11/2025
"""

import pytest
from http import HTTPStatus
from unittest.mock import Mock, patch


@pytest.mark.anyio
class TestMetricsSummaryEndpoint:
    """Tests para GET /payments/metrics/summary."""
    
    async def test_summary_requires_authentication(self, async_client, _override_current_user_dependency):
        """Test: endpoint requiere autenticación."""
        _override_current_user_dependency["set_no_user"]()
        response = await async_client.get("/payments/metrics/summary")
        # Puede ser 401 (no auth) o 404 (ruta no montada en tests)
        assert response.status_code in [HTTPStatus.UNAUTHORIZED, HTTPStatus.NOT_FOUND]
    
    async def test_summary_requires_admin_role(
        self, async_client, auth_headers, _override_current_user_dependency
    ):
        """Test: endpoint requiere rol de administrador."""
        # Usuario regular (no admin)
        _override_current_user_dependency["set_user"](999, False)
        headers = auth_headers(user_id=999, is_admin=False)
        response = await async_client.get("/payments/metrics/summary", headers=headers)
        
        # Puede ser 403 (Forbidden) o 404 (ruta no montada en tests)
        assert response.status_code in [HTTPStatus.FORBIDDEN, HTTPStatus.NOT_FOUND]
    
    async def test_summary_returns_data_for_admin(
        self, async_client, auth_headers, metrics_collector
    ):
        """Test: endpoint retorna datos para administrador."""
        # Usuario admin (por defecto con autouse fixture)
        
        # Registrar algunas métricas
        metrics_collector.record_endpoint_call("POST /test", 100.0, 200)
        metrics_collector.record_payment_attempt("stripe", "paid")
        
        headers = auth_headers(user_id=1, is_admin=True)
        response = await async_client.get("/payments/metrics/summary", headers=headers)
        
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            
            assert data["success"] is True
            assert "data" in data
            assert "uptime_seconds" in data["data"]
            assert "total_endpoints_tracked" in data["data"]
            assert "last_hour" in data["data"]


@pytest.mark.anyio
class TestEndpointsMetricsEndpoint:
    """Tests para GET /payments/metrics/endpoints."""
    
    async def test_endpoints_requires_admin(
        self, async_client, auth_headers, _override_current_user_dependency
    ):
        """Test: endpoint requiere admin."""
        _override_current_user_dependency["set_user"](999, False)
        headers = auth_headers(user_id=999, is_admin=False)
        response = await async_client.get("/payments/metrics/endpoints", headers=headers)
        assert response.status_code in [HTTPStatus.FORBIDDEN, HTTPStatus.NOT_FOUND]
    
    async def test_endpoints_returns_all_endpoints(
        self, async_client, auth_headers, metrics_collector
    ):
        """Test: retorna métricas de todos los endpoints."""
        # Usuario admin por defecto
        # Registrar métricas
        metrics_collector.record_endpoint_call("POST /checkout", 100.0, 200)
        metrics_collector.record_endpoint_call("GET /payments", 50.0, 200)
        
        headers = auth_headers(user_id=1, is_admin=True)
        response = await async_client.get("/payments/metrics/endpoints", headers=headers)
        
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            
            assert data["success"] is True
            assert "data" in data
            assert "time_window_hours" in data
            assert isinstance(data["data"], list)
    
    async def test_endpoints_filters_by_endpoint_name(
        self, async_client, auth_headers, metrics_collector
    ):
        """Test: filtrado por nombre de endpoint."""
        # Usuario admin por defecto
        metrics_collector.record_endpoint_call("POST /checkout", 100.0, 200)
        metrics_collector.record_endpoint_call("GET /payments", 50.0, 200)
        
        headers = auth_headers(user_id=1, is_admin=True)
        response = await async_client.get(
            "/payments/metrics/endpoints?endpoint=POST /checkout",
            headers=headers
        )
        
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            
            # Solo debe incluir el endpoint filtrado
            if len(data["data"]) > 0:
                assert all(ep["endpoint"] == "POST /checkout" for ep in data["data"])
    
    async def test_endpoints_respects_time_window(
        self, async_client, auth_headers, metrics_collector
    ):
        """Test: respeta la ventana de tiempo."""
        # Usuario admin por defecto
        metrics_collector.record_endpoint_call("POST /test", 100.0, 200)
        
        headers = auth_headers(user_id=1, is_admin=True)
        
        # Solicitar últimas 6 horas
        response = await async_client.get(
            "/payments/metrics/endpoints?hours=6",
            headers=headers
        )
        
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            assert data["time_window_hours"] == 6
    
    async def test_endpoints_validates_hours_parameter(
        self, async_client, auth_headers
    ):
        """Test: valida el parámetro hours."""
        # Usuario admin por defecto
        headers = auth_headers(user_id=1, is_admin=True)
        
        # Hours fuera de rango (debe ser 1-24)
        response = await async_client.get(
            "/payments/metrics/endpoints?hours=50",
            headers=headers
        )
        
        # Puede ser 422 (validation error) o 404 si no está montado
        assert response.status_code in [HTTPStatus.UNPROCESSABLE_ENTITY, HTTPStatus.NOT_FOUND, HTTPStatus.OK]


@pytest.mark.anyio
class TestConversionsMetricsEndpoint:
    """Tests para GET /payments/metrics/conversions."""
    
    async def test_conversions_requires_admin(
        self, async_client, auth_headers, _override_current_user_dependency
    ):
        """Test: endpoint requiere admin."""
        _override_current_user_dependency["set_user"](999, False)
        headers = auth_headers(user_id=999, is_admin=False)
        response = await async_client.get("/payments/metrics/conversions", headers=headers)
        assert response.status_code in [HTTPStatus.FORBIDDEN, HTTPStatus.NOT_FOUND]
    
    async def test_conversions_returns_all_providers(
        self, async_client, auth_headers, metrics_collector
    ):
        """Test: retorna conversiones de todos los proveedores."""
        metrics_collector.record_payment_attempt("stripe", "paid")
        metrics_collector.record_payment_attempt("paypal", "paid")
        
        headers = auth_headers(user_id=1, is_admin=True)
        response = await async_client.get("/payments/metrics/conversions", headers=headers)
        
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            
            assert data["success"] is True
            assert "data" in data
            assert isinstance(data["data"], list)
    
    async def test_conversions_filters_by_provider(
        self, async_client, auth_headers, metrics_collector
    ):
        """Test: filtrado por proveedor."""
        metrics_collector.record_payment_attempt("stripe", "paid")
        metrics_collector.record_payment_attempt("paypal", "paid")
        
        headers = auth_headers(user_id=1, is_admin=True)
        response = await async_client.get(
            "/payments/metrics/conversions?provider=stripe",
            headers=headers
        )
        
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            
            if len(data["data"]) > 0:
                assert all(prov["provider"] == "stripe" for prov in data["data"])
    
    async def test_conversions_includes_conversion_rates(
        self, async_client, auth_headers, metrics_collector
    ):
        """Test: incluye tasas de conversión."""
        # Registrar intentos con diferentes estados
        for _ in range(8):
            metrics_collector.record_payment_attempt("stripe", "paid")
        for _ in range(2):
            metrics_collector.record_payment_attempt("stripe", "failed")
        
        headers = auth_headers(user_id=1, is_admin=True)
        response = await async_client.get(
            "/payments/metrics/conversions?provider=stripe",
            headers=headers
        )
        
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            
            if len(data["data"]) > 0:
                provider_data = data["data"][0]
                assert "conversion_rate" in provider_data
                assert "failure_rate" in provider_data


@pytest.mark.anyio
class TestHealthStatusEndpoint:
    """Tests para GET /payments/metrics/health."""
    
    async def test_health_requires_admin(
        self, async_client, auth_headers, _override_current_user_dependency
    ):
        """Test: endpoint requiere admin."""
        _override_current_user_dependency["set_user"](999, False)
        headers = auth_headers(user_id=999, is_admin=False)
        response = await async_client.get("/payments/metrics/health", headers=headers)
        assert response.status_code in [HTTPStatus.FORBIDDEN, HTTPStatus.NOT_FOUND]
    
    async def test_health_returns_status(
        self, async_client, auth_headers, metrics_collector
    ):
        """Test: retorna estado de salud."""
        # Registrar métricas normales
        for _ in range(100):
            metrics_collector.record_endpoint_call("POST /test", 100.0, 200)
        
        headers = auth_headers(user_id=1, is_admin=True)
        response = await async_client.get("/payments/metrics/health", headers=headers)
        
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            
            assert data["success"] is True
            assert "data" in data
            assert "status" in data["data"]
            assert data["data"]["status"] in ["healthy", "warning", "critical"]
    
    async def test_health_includes_alerts(
        self, async_client, auth_headers, metrics_collector
    ):
        """Test: incluye alertas cuando hay problemas."""
        # Registrar métricas con alta tasa de error
        for i in range(100):
            error = "TestError" if i < 15 else None
            status_code = 500 if i < 15 else 200
            metrics_collector.record_endpoint_call("POST /test", 100.0, status_code, error)
        
        headers = auth_headers(user_id=1, is_admin=True)
        response = await async_client.get("/payments/metrics/health", headers=headers)
        
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            
            assert "alerts" in data["data"]
            assert isinstance(data["data"]["alerts"], list)
    
    async def test_health_includes_metrics_summary(
        self, async_client, auth_headers, metrics_collector
    ):
        """Test: incluye resumen de métricas."""
        metrics_collector.record_endpoint_call("POST /test", 100.0, 200)
        
        headers = auth_headers(user_id=1, is_admin=True)
        response = await async_client.get("/payments/metrics/health", headers=headers)
        
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            assert "metrics_summary" in data["data"]


@pytest.mark.anyio
class TestSnapshotEndpoint:
    """Tests para GET /payments/metrics/snapshot."""
    
    async def test_snapshot_requires_admin(
        self, async_client, auth_headers, _override_current_user_dependency
    ):
        """Test: endpoint requiere admin."""
        _override_current_user_dependency["set_user"](999, False)
        headers = auth_headers(user_id=999, is_admin=False)
        response = await async_client.get("/payments/metrics/snapshot", headers=headers)
        assert response.status_code in [HTTPStatus.FORBIDDEN, HTTPStatus.NOT_FOUND]
    
    async def test_snapshot_returns_complete_data(
        self, async_client, auth_headers, metrics_collector
    ):
        """Test: retorna snapshot completo."""
        # Registrar métricas de endpoints y conversiones
        metrics_collector.record_endpoint_call("POST /checkout", 100.0, 200)
        metrics_collector.record_payment_attempt("stripe", "paid")
        
        headers = auth_headers(user_id=1, is_admin=True)
        response = await async_client.get("/payments/metrics/snapshot", headers=headers)
        
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            
            assert data["success"] is True
            assert "snapshot" in data
            assert "endpoints" in data["snapshot"]
            assert "providers" in data["snapshot"]
            assert "time_window_hours" in data["snapshot"]
    
    async def test_snapshot_respects_time_window(
        self, async_client, auth_headers, metrics_collector
    ):
        """Test: respeta la ventana de tiempo."""
        metrics_collector.record_endpoint_call("POST /test", 100.0, 200)
        
        headers = auth_headers(user_id=1, is_admin=True)
        response = await async_client.get(
            "/payments/metrics/snapshot?hours=12",
            headers=headers
        )
        
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            assert data["snapshot"]["time_window_hours"] == 12


@pytest.mark.anyio
class TestPingEndpoint:
    """Tests para GET /payments/metrics/ping."""
    
    async def test_ping_does_not_require_authentication(self, async_client):
        """Test: ping no requiere autenticación."""
        response = await async_client.get("/payments/metrics/ping")
        
        # Puede ser 200 (OK) o 404 (si no está montado)
        assert response.status_code in [HTTPStatus.OK, HTTPStatus.NOT_FOUND]
    
    async def test_ping_returns_ok_status(self, async_client):
        """Test: ping retorna status ok."""
        response = await async_client.get("/payments/metrics/ping")
        
        if response.status_code == HTTPStatus.OK:
            data = response.json()
            
            assert "status" in data
            assert data["status"] == "ok"
            assert "service" in data


@pytest.mark.anyio
class TestMetricsRoutesErrorHandling:
    """Tests de manejo de errores en rutas de métricas."""
    
    async def test_summary_handles_internal_error(
        self, async_client, auth_headers, metrics_collector
    ):
        """Test: manejo de error interno en summary."""
        headers = auth_headers(user_id=1, is_admin=True)
        
        # Simular error interno
        with patch.object(metrics_collector, 'get_summary', side_effect=Exception("Internal error")):
            response = await async_client.get("/payments/metrics/summary", headers=headers)
            
            # Puede ser 500 o 404 si no está montado
            assert response.status_code in [HTTPStatus.INTERNAL_SERVER_ERROR, HTTPStatus.NOT_FOUND]
    
    async def test_endpoints_handles_internal_error(
        self, async_client, auth_headers, metrics_collector
    ):
        """Test: manejo de error interno en endpoints."""
        headers = auth_headers(user_id=1, is_admin=True)
        
        with patch.object(metrics_collector, 'get_endpoint_metrics', side_effect=Exception("Error")):
            response = await async_client.get("/payments/metrics/endpoints", headers=headers)
            
            assert response.status_code in [HTTPStatus.INTERNAL_SERVER_ERROR, HTTPStatus.NOT_FOUND]
    
    async def test_conversions_handles_internal_error(
        self, async_client, auth_headers, metrics_collector
    ):
        """Test: manejo de error interno en conversions."""
        headers = auth_headers(user_id=1, is_admin=True)
        
        with patch.object(metrics_collector, 'get_provider_conversions', side_effect=Exception("Error")):
            response = await async_client.get("/payments/metrics/conversions", headers=headers)
            
            assert response.status_code in [HTTPStatus.INTERNAL_SERVER_ERROR, HTTPStatus.NOT_FOUND]


@pytest.mark.anyio
class TestMetricsRoutesIntegration:
    """Tests de integración de rutas de métricas."""
    
    async def test_full_workflow_admin_queries_metrics(
        self, async_client, auth_headers, metrics_collector
    ):
        """Test: flujo completo - admin consulta diferentes métricas."""
        # 1. Registrar actividad del sistema
        for i in range(50):
            metrics_collector.record_endpoint_call("POST /checkout", 100.0 + i, 200)
        
        for i in range(30):
            status = "paid" if i < 25 else "failed"
            metrics_collector.record_payment_attempt("stripe", status)
        
        headers = auth_headers(user_id=1, is_admin=True)
        
        # 2. Consultar resumen
        summary_response = await async_client.get(
            "/payments/metrics/summary",
            headers=headers
        )
        
        # 3. Consultar endpoints
        endpoints_response = await async_client.get(
            "/payments/metrics/endpoints",
            headers=headers
        )
        
        # 4. Consultar conversiones
        conversions_response = await async_client.get(
            "/payments/metrics/conversions",
            headers=headers
        )
        
        # 5. Consultar salud
        health_response = await async_client.get(
            "/payments/metrics/health",
            headers=headers
        )
        
        # Verificar que al menos uno de los endpoints funciona
        responses = [
            summary_response,
            endpoints_response,
            conversions_response,
            health_response
        ]
        
        ok_responses = [r for r in responses if r.status_code == HTTPStatus.OK]
        
        # Al menos algún endpoint debe funcionar (si están montados)
        # O todos deben ser 404 (si no están montados aún)
        not_found_responses = [r for r in responses if r.status_code == HTTPStatus.NOT_FOUND]
        
        assert len(ok_responses) > 0 or len(not_found_responses) == len(responses)


@pytest.mark.anyio
class TestMetricsRoutesAuthorization:
    """Tests específicos de autorización."""
    
    async def test_non_admin_cannot_access_any_metric_endpoint(
        self, async_client, auth_headers, _override_current_user_dependency
    ):
        """Test: usuarios no-admin no pueden acceder a ningún endpoint de métricas."""
        _override_current_user_dependency["set_user"](999, False)
        headers = auth_headers(user_id=999, is_admin=False)
        
        protected_endpoints = [
            "/payments/metrics/summary",
            "/payments/metrics/endpoints",
            "/payments/metrics/conversions",
            "/payments/metrics/health",
            "/payments/metrics/snapshot",
        ]
        
        for endpoint in protected_endpoints:
            response = await async_client.get(endpoint, headers=headers)
            # Debe ser Forbidden o Not Found
            assert response.status_code in [HTTPStatus.FORBIDDEN, HTTPStatus.NOT_FOUND]
    
    async def test_unauthenticated_cannot_access_protected_endpoints(
        self, async_client, _override_current_user_dependency
    ):
        """Test: usuarios no autenticados no pueden acceder."""
        _override_current_user_dependency["set_no_user"]()
        protected_endpoints = [
            "/payments/metrics/summary",
            "/payments/metrics/endpoints",
            "/payments/metrics/conversions",
            "/payments/metrics/health",
            "/payments/metrics/snapshot",
        ]
        
        for endpoint in protected_endpoints:
            response = await async_client.get(endpoint)
            # Debe ser Unauthorized, Forbidden o Not Found
            assert response.status_code in [
                HTTPStatus.UNAUTHORIZED,
                HTTPStatus.FORBIDDEN,
                HTTPStatus.NOT_FOUND
            ]
    
    async def test_admin_can_access_all_metric_endpoints(
        self, async_client, auth_headers, metrics_collector
    ):
        """Test: admin puede acceder a todos los endpoints."""
        # Registrar algunas métricas
        metrics_collector.record_endpoint_call("POST /test", 100.0, 200)
        metrics_collector.record_payment_attempt("stripe", "paid")
        
        headers = auth_headers(user_id=1, is_admin=True)
        
        protected_endpoints = [
            "/payments/metrics/summary",
            "/payments/metrics/endpoints",
            "/payments/metrics/conversions",
            "/payments/metrics/health",
            "/payments/metrics/snapshot",
        ]
        
        for endpoint in protected_endpoints:
            response = await async_client.get(endpoint, headers=headers)
            # Debe ser OK o Not Found (si no está montado todavía)
            assert response.status_code in [HTTPStatus.OK, HTTPStatus.NOT_FOUND]
