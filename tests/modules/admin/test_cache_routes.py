# -*- coding: utf-8 -*-
"""
tests/modules/admin/test_cache_routes.py

Tests para los endpoints administrativos de caché.

Cubre:
- Autenticación con admin key
- GET /api/admin/cache/stats
- GET /api/admin/cache/health
- POST /api/admin/cache/clear
- POST /api/admin/cache/invalidate
- POST /api/admin/cache/reset-stats
"""

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from app.modules.admin.routes.cache_routes import router
from app.modules.files.services.cache import get_metadata_cache, reset_global_cache


@pytest.fixture
def app():
    """FastAPI app para tests."""
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return app


@pytest.fixture
def client(app):
    """TestClient para hacer requests."""
    return TestClient(app)


@pytest.fixture
def admin_headers():
    """Headers con clave de admin válida."""
    return {"X-Admin-Key": "dev-admin-key-change-in-production"}


@pytest.fixture(autouse=True)
def reset_cache():
    """Limpia el caché antes y después de cada test."""
    reset_global_cache()
    yield
    reset_global_cache()


def test_get_stats_without_auth(client):
    """Debe rechazar requests sin autenticación."""
    response = client.get("/api/admin/cache/stats")
    assert response.status_code == 401
    assert "Missing X-Admin-Key" in response.json()["detail"]


def test_get_stats_with_invalid_key(client):
    """Debe rechazar requests con clave inválida."""
    response = client.get(
        "/api/admin/cache/stats",
        headers={"X-Admin-Key": "invalid-key"}
    )
    assert response.status_code == 403
    assert "Invalid admin key" in response.json()["detail"]


def test_get_stats_success(client, admin_headers):
    """Debe retornar estadísticas del caché."""
    # Preparar: agregar algunas entradas al caché
    cache = get_metadata_cache()
    cache.set("test1", "value1")
    cache.set("test2", "value2")
    cache.get("test1")  # hit
    cache.get("nonexistent")  # miss
    
    response = client.get("/api/admin/cache/stats", headers=admin_headers)
    
    assert response.status_code == 200
    data = response.json()
    
    assert "size" in data
    assert "max_size" in data
    assert "hits" in data
    assert "misses" in data
    assert "hit_rate_percent" in data
    assert "evictions" in data
    assert "invalidations" in data
    assert "total_requests" in data
    
    assert data["size"] == 2
    assert data["hits"] == 1
    assert data["misses"] == 1


def test_get_health_success(client, admin_headers):
    """Debe retornar estado de salud del caché."""
    response = client.get("/api/admin/cache/health", headers=admin_headers)
    
    assert response.status_code == 200
    data = response.json()
    
    assert "status" in data
    assert data["status"] in ["healthy", "degraded", "critical"]
    assert "size" in data
    assert "capacity_percent" in data
    assert "hit_rate_percent" in data
    assert "warnings" in data
    assert isinstance(data["warnings"], list)


def test_get_health_with_warnings(client, admin_headers):
    """Debe retornar warnings cuando el caché está degradado."""
    cache = get_metadata_cache()
    
    # Llenar el caché al 95%
    max_size = cache.get_stats()["max_size"]
    for i in range(int(max_size * 0.95)):
        cache.set(f"key{i}", f"value{i}")
    
    response = client.get("/api/admin/cache/health", headers=admin_headers)
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] in ["degraded", "critical"]
    assert len(data["warnings"]) > 0
    assert any("casi lleno" in w.lower() for w in data["warnings"])


def test_clear_cache_success(client, admin_headers):
    """Debe limpiar el caché completamente."""
    cache = get_metadata_cache()
    
    # Agregar entradas
    for i in range(10):
        cache.set(f"key{i}", f"value{i}")
    
    assert cache.get_stats()["size"] == 10
    
    response = client.post("/api/admin/cache/clear", headers=admin_headers)
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["cleared_count"] == 10
    assert "successfully" in data["message"].lower()
    
    # Verificar que el caché está vacío
    assert cache.get_stats()["size"] == 0


def test_invalidate_by_pattern_success(client, admin_headers):
    """Debe invalidar entradas por patrón."""
    cache = get_metadata_cache()
    
    # Agregar entradas con diferentes prefijos
    cache.set("input_meta:1", "value1")
    cache.set("input_meta:2", "value2")
    cache.set("product_meta:1", "value3")
    cache.set("product_meta:2", "value4")
    
    assert cache.get_stats()["size"] == 4
    
    response = client.post(
        "/api/admin/cache/invalidate",
        headers=admin_headers,
        json={"pattern": "input_meta:"}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["invalidated_count"] == 2
    assert data["pattern"] == "input_meta:"
    
    # Verificar que solo quedaron las entradas de product
    assert cache.get_stats()["size"] == 2
    assert cache.get("product_meta:1") == "value3"
    assert cache.get("product_meta:2") == "value4"
    assert cache.get("input_meta:1") is None
    assert cache.get("input_meta:2") is None


def test_invalidate_with_empty_pattern(client, admin_headers):
    """Debe rechazar patrón vacío."""
    response = client.post(
        "/api/admin/cache/invalidate",
        headers=admin_headers,
        json={"pattern": ""}
    )
    
    assert response.status_code == 422  # Validation error


def test_reset_stats_success(client, admin_headers):
    """Debe reiniciar las estadísticas del caché."""
    cache = get_metadata_cache()
    
    # Generar actividad
    cache.set("key1", "value1")
    cache.get("key1")
    cache.get("nonexistent")
    
    stats_before = cache.get_stats()
    assert stats_before["hits"] > 0
    assert stats_before["misses"] > 0
    
    response = client.post("/api/admin/cache/reset-stats", headers=admin_headers)
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] == "ok"
    assert "successfully" in data["message"].lower()
    
    # Verificar que las stats se reiniciaron
    stats_after = cache.get_stats()
    assert stats_after["hits"] == 0
    assert stats_after["misses"] == 0
    assert stats_after["evictions"] == 0
    assert stats_after["invalidations"] == 0
    
    # Pero el caché aún tiene datos
    assert cache.get("key1") == "value1"


def test_all_endpoints_require_auth(client):
    """Todos los endpoints deben requerir autenticación."""
    endpoints = [
        ("GET", "/api/admin/cache/stats"),
        ("GET", "/api/admin/cache/health"),
        ("POST", "/api/admin/cache/clear"),
        ("POST", "/api/admin/cache/invalidate"),
        ("POST", "/api/admin/cache/reset-stats"),
    ]
    
    for method, path in endpoints:
        if method == "GET":
            response = client.get(path)
        else:
            response = client.post(path, json={})
        
        assert response.status_code in [401, 403, 422], \
            f"{method} {path} should require authentication"


# Fin del archivo tests/modules/admin/test_cache_routes.py
