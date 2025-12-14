# -*- coding: utf-8 -*-
"""
backend/tests/modules/payments/monitoring/conftest.py

Fixtures compartidas para tests de métricas.

Autor: Ixchel Beristáin
Fecha: 06/11/2025
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock

from app.modules.payments.metrics.aggregators import (
    MetricsStorage,
    LatencyBucket,
    ConversionBucket,
    TimeWindow,
)
from app.modules.payments.metrics.collectors.metrics_collector import MetricsCollector


@pytest.fixture
def metrics_storage():
    """Instancia limpia de MetricsStorage para cada test."""
    return MetricsStorage(retention_hours=24)


@pytest.fixture
def metrics_collector(monkeypatch):
    """Instancia limpia de MetricsCollector para cada test."""
    # Reset singleton para cada test
    MetricsCollector._instance = None
    # También resetear el flag de inicialización si existe
    if hasattr(MetricsCollector, '_initialized'):
        MetricsCollector._initialized = False
    
    # Crear nueva instancia
    collector = MetricsCollector(retention_hours=24)
    
    # Hacer que get_metrics_collector() devuelva esta instancia
    from app.modules.payments.metrics.collectors import metrics_collector as mc_module
    monkeypatch.setattr(mc_module, '_metrics_collector', collector)
    monkeypatch.setattr(mc_module, 'get_metrics_collector', lambda: collector)
    
    return collector


@pytest.fixture
def latency_bucket():
    """Bucket de latencias vacío."""
    return LatencyBucket()


@pytest.fixture
def conversion_bucket():
    """Bucket de conversiones vacío."""
    return ConversionBucket()


@pytest.fixture
def sample_latencies():
    """Lista de latencias de ejemplo para tests de percentiles."""
    return [100, 120, 150, 180, 200, 250, 300, 400, 500, 1000]


@pytest.fixture
def mock_user_admin():
    """Mock de usuario administrador."""
    user = Mock()
    user.id = 1
    user.is_admin = True
    user.role = "admin"
    return user


@pytest.fixture
def mock_user_regular():
    """Mock de usuario regular (no admin)."""
    user = Mock()
    user.id = 2
    user.is_admin = False
    user.role = "user"
    return user


@pytest.fixture
def mock_async_session():
    """Mock de AsyncSession para tests."""
    session = MagicMock()
    return session


@pytest.fixture
def sample_endpoint_metrics():
    """Métricas de ejemplo para un endpoint."""
    return {
        "POST /payments/checkout": {
            "total_requests": 100,
            "total_errors": 5,
            "error_rate": 5.0,
            "latency": {
                "p50": 120.0,
                "p95": 450.0,
                "p99": 890.0,
                "avg": 180.0,
            },
            "errors_by_type": {
                "ValidationError": 3,
                "HTTP_500": 2,
            },
        }
    }


@pytest.fixture
def sample_conversion_metrics():
    """Métricas de conversión de ejemplo."""
    return {
        "stripe": {
            "total_attempts": 100,
            "successful": 85,
            "failed": 10,
            "pending": 3,
            "cancelled": 2,
            "conversion_rate": 85.0,
            "failure_rate": 10.0,
        }
    }


@pytest.fixture
def datetime_now():
    """Timestamp fijo para tests."""
    return datetime(2025, 11, 6, 12, 0, 0)


@pytest.fixture
def datetime_one_hour_ago(datetime_now):
    """Timestamp de hace una hora."""
    return datetime_now - timedelta(hours=1)


@pytest.fixture
def datetime_24_hours_ago(datetime_now):
    """Timestamp de hace 24 horas."""
    return datetime_now - timedelta(hours=24)


@pytest.fixture(autouse=True)
def setup_admin_user_for_metrics_tests(app, monkeypatch):
    """Auto-setup de usuario admin para todos los tests de métricas."""
    from unittest.mock import Mock
    
    # Mock del usuario admin por defecto
    mock_admin = Mock()
    mock_admin.id = 1
    mock_admin.is_admin = True
    mock_admin.role = "admin"
    
    def get_test_user():
        return mock_admin
    
    # Parchear la dependencia de forma lazy (solo cuando se importe)
    def patch_metrics_module():
        try:
            from app.modules.payments.routes import metrics as metrics_routes
            monkeypatch.setattr(metrics_routes, "get_current_user", lambda: get_test_user)
        except ImportError:
            pass  # El módulo aún no está disponible
    
    # Intentar parchear ahora
    patch_metrics_module()


@pytest.fixture
def auth_headers():
    """Genera headers de autenticación para tests."""
    def _make_headers(user_id: int = 1, is_admin: bool = True):
        return {
            "Authorization": f"Bearer test-token-{user_id}",
            "X-User-ID": str(user_id),
            "X-Is-Admin": str(is_admin).lower(),
        }
    return _make_headers


@pytest.fixture
def _override_current_user_dependency(app):
    """Override de get_current_user y get_current_user_admin para tests de rutas (control manual)."""
    
    # Modificar el estado del admin en el fixture autouse
    if hasattr(app, '_admin_state'):
        admin_state = app._admin_state
        
        # IMPORTANTE: También sobrescribir las referencias locales en los módulos de métricas
        # para asegurar que el override funcione correctamente
        async def admin_test_override():
            """Override para tests - usa el estado mutable del fixture autouse."""
            from unittest.mock import Mock
            from fastapi import HTTPException, status
            
            user = Mock()
            user.id = admin_state.user_id
            user.is_admin = admin_state.is_admin
            user.role = "admin" if admin_state.is_admin else "user"
            
            if not admin_state.is_admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not enough permissions"
                )
            return user
        
        # Sobrescribir en los módulos que lo usan
        try:
            from app.modules.payments.metrics.routes import routes_snapshot_memory
            if hasattr(routes_snapshot_memory, 'get_current_user_admin'):
                original_memory = routes_snapshot_memory.get_current_user_admin
                app.dependency_overrides[original_memory] = admin_test_override
        except (ImportError, AttributeError):
            pass
        
        try:
            from app.modules.payments.metrics.routes import routes_snapshot_db
            if hasattr(routes_snapshot_db, 'get_current_user_admin'):
                original_db = routes_snapshot_db.get_current_user_admin
                app.dependency_overrides[original_db] = admin_test_override
        except (ImportError, AttributeError):
            pass
        
        # Retornar funciones para controlar el mock
        def set_user(user_id: int, is_admin: bool):
            admin_state.is_admin = is_admin
            admin_state.user_id = user_id
        
        def set_no_user():
            admin_state.is_admin = False
            admin_state.user_id = None
        
        controls = {
            "set_user": set_user,
            "set_no_user": set_no_user,
        }
        
        yield controls
        
        # Restaurar estado original
        admin_state.is_admin = True
        admin_state.user_id = 1
    else:
        # Fallback si no hay _admin_state
        yield {
            "set_user": lambda user_id, is_admin: None,
            "set_no_user": lambda: None,
        }
