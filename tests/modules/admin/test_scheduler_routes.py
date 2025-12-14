# -*- coding: utf-8 -*-
"""
Tests para endpoints de monitoreo del scheduler.

Cubre:
- GET /api/admin/scheduler/jobs - Listar jobs activos
- GET /api/admin/scheduler/jobs/{job_id} - Estado de job individual
- POST /api/admin/scheduler/jobs/{job_id}/pause - Pausar job
- POST /api/admin/scheduler/jobs/{job_id}/resume - Reanudar job
- POST /api/admin/scheduler/jobs/{job_id}/run-now - Ejecutar job manualmente
- GET /api/admin/scheduler/stats/cache-cleanup - Estadísticas históricas
- GET /api/admin/scheduler/health - Salud del scheduler
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from app.modules.admin.routes.scheduler_routes import router


@pytest.fixture
def app():
    """Crea app FastAPI con router de scheduler."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Crea cliente de pruebas."""
    return TestClient(app)


@pytest.fixture
def mock_admin_key(monkeypatch):
    """Mock de API key de admin."""
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key-123")
    return "test-admin-key-123"


@pytest.fixture
def mock_scheduler():
    """Mock del scheduler."""
    scheduler = Mock()
    scheduler.is_running = True
    scheduler.get_jobs.return_value = [
        {
            "id": "cache_cleanup_hourly",
            "name": "cache_cleanup_hourly",
            "next_run": "2025-11-05T15:00:00",
            "trigger": "interval[1:00:00]"
        }
    ]
    scheduler.get_job_status.return_value = {
        "id": "cache_cleanup_hourly",
        "name": "cache_cleanup_hourly",
        "next_run": "2025-11-05T15:00:00",
        "trigger": "interval[1:00:00]",
        "pending": False
    }
    return scheduler


# ==================== AUTENTICACIÓN ====================

def test_list_jobs_requires_admin_key(client, mock_admin_key):
    """Verifica que se requiere API key de admin."""
    response = client.get("/admin/scheduler/jobs")
    assert response.status_code == 422  # Sin header
    
    response = client.get(
        "/admin/scheduler/jobs",
        headers={"X-Admin-Key": "wrong-key"}
    )
    assert response.status_code == 401
    assert "inválida" in response.json()["detail"]


# ==================== LISTAR JOBS ====================

def test_list_scheduled_jobs(client, mock_admin_key, mock_scheduler):
    """Verifica que se pueden listar los jobs activos."""
    with patch("app.modules.admin.routes.scheduler_routes.get_scheduler", return_value=mock_scheduler):
        response = client.get(
            "/admin/scheduler/jobs",
            headers={"X-Admin-Key": mock_admin_key}
        )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["is_running"] is True
    assert len(data["jobs"]) == 1
    assert data["jobs"][0]["id"] == "cache_cleanup_hourly"


def test_list_jobs_when_scheduler_not_running(client, mock_admin_key, mock_scheduler):
    """Verifica respuesta cuando el scheduler no está activo."""
    mock_scheduler.is_running = False
    
    with patch("app.modules.admin.routes.scheduler_routes.get_scheduler", return_value=mock_scheduler):
        response = client.get(
            "/admin/scheduler/jobs",
            headers={"X-Admin-Key": mock_admin_key}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["is_running"] is False


# ==================== ESTADO DE JOB INDIVIDUAL ====================

def test_get_job_status(client, mock_admin_key, mock_scheduler):
    """Verifica que se puede obtener estado de un job específico."""
    with patch("app.modules.admin.routes.scheduler_routes.get_scheduler", return_value=mock_scheduler):
        response = client.get(
            "/admin/scheduler/jobs/cache_cleanup_hourly",
            headers={"X-Admin-Key": mock_admin_key}
        )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["id"] == "cache_cleanup_hourly"
    assert "next_run" in data
    assert "trigger" in data


def test_get_job_status_not_found(client, mock_admin_key, mock_scheduler):
    """Verifica error 404 cuando el job no existe."""
    mock_scheduler.get_job_status.return_value = None
    
    with patch("app.modules.admin.routes.scheduler_routes.get_scheduler", return_value=mock_scheduler):
        response = client.get(
            "/admin/scheduler/jobs/nonexistent_job",
            headers={"X-Admin-Key": mock_admin_key}
        )
    
    assert response.status_code == 404
    assert "no encontrado" in response.json()["detail"]


# ==================== PAUSAR/REANUDAR JOB ====================

def test_pause_job(client, mock_admin_key, mock_scheduler):
    """Verifica que se puede pausar un job."""
    with patch("app.modules.admin.routes.scheduler_routes.get_scheduler", return_value=mock_scheduler):
        response = client.post(
            "/admin/scheduler/jobs/cache_cleanup_hourly/pause",
            headers={"X-Admin-Key": mock_admin_key}
        )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["job_id"] == "cache_cleanup_hourly"
    assert data["status"] == "paused"
    mock_scheduler._scheduler.pause_job.assert_called_once_with("cache_cleanup_hourly")


def test_resume_job(client, mock_admin_key, mock_scheduler):
    """Verifica que se puede reanudar un job."""
    with patch("app.modules.admin.routes.scheduler_routes.get_scheduler", return_value=mock_scheduler):
        response = client.post(
            "/admin/scheduler/jobs/cache_cleanup_hourly/resume",
            headers={"X-Admin-Key": mock_admin_key}
        )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["job_id"] == "cache_cleanup_hourly"
    assert data["status"] == "active"
    mock_scheduler._scheduler.resume_job.assert_called_once_with("cache_cleanup_hourly")


# ==================== EJECUTAR JOB MANUALMENTE ====================

@pytest.mark.asyncio
async def test_run_job_now(client, mock_admin_key, mock_scheduler):
    """Verifica que se puede ejecutar un job manualmente."""
    mock_job = Mock()
    mock_job.func = AsyncMock(return_value={
        "entries_removed": 150,
        "memory_freed_kb": 300
    })
    mock_job.kwargs = {}
    
    mock_scheduler._scheduler.get_job.return_value = mock_job
    
    with patch("app.modules.admin.routes.scheduler_routes.get_scheduler", return_value=mock_scheduler):
        response = client.post(
            "/admin/scheduler/jobs/cache_cleanup_hourly/run-now",
            headers={"X-Admin-Key": mock_admin_key}
        )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["job_id"] == "cache_cleanup_hourly"
    assert "result" in data
    assert data["result"]["entries_removed"] == 150


def test_run_job_now_not_found(client, mock_admin_key, mock_scheduler):
    """Verifica error cuando el job a ejecutar no existe."""
    mock_scheduler._scheduler.get_job.return_value = None
    
    with patch("app.modules.admin.routes.scheduler_routes.get_scheduler", return_value=mock_scheduler):
        response = client.post(
            "/admin/scheduler/jobs/nonexistent/run-now",
            headers={"X-Admin-Key": mock_admin_key}
        )
    
    assert response.status_code == 404


# ==================== ESTADÍSTICAS ====================

def test_get_cache_cleanup_stats(client, mock_admin_key):
    """Verifica que se pueden obtener estadísticas históricas."""
    mock_cache = Mock()
    mock_cache.get_stats.return_value = {
        "size": 800,
        "hits": 400,
        "misses": 100,
        "total": 500,
        "hit_rate": 80.0,
        "evictions": 10
    }
    
    with patch("app.modules.admin.routes.scheduler_routes.get_metadata_cache", return_value=mock_cache):
        response = client.get(
            "/admin/scheduler/stats/cache-cleanup?days=7",
            headers={"X-Admin-Key": mock_admin_key}
        )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "period" in data
    assert data["period"]["days"] == 7
    assert "summary" in data
    assert "history" in data
    assert isinstance(data["summary"]["total_executions"], int)


# ==================== SALUD DEL SCHEDULER ====================

def test_scheduler_health_healthy(client, mock_admin_key, mock_scheduler):
    """Verifica estado de salud cuando todo está OK."""
    with patch("app.modules.admin.routes.scheduler_routes.get_scheduler", return_value=mock_scheduler):
        response = client.get(
            "/admin/scheduler/health",
            headers={"X-Admin-Key": mock_admin_key}
        )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] == "healthy"
    assert data["is_running"] is True
    assert data["jobs_count"] == 1
    assert len(data["warnings"]) == 0


def test_scheduler_health_unhealthy_when_not_running(client, mock_admin_key, mock_scheduler):
    """Verifica estado unhealthy cuando el scheduler no está activo."""
    mock_scheduler.is_running = False
    
    with patch("app.modules.admin.routes.scheduler_routes.get_scheduler", return_value=mock_scheduler):
        response = client.get(
            "/admin/scheduler/health",
            headers={"X-Admin-Key": mock_admin_key}
        )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] == "unhealthy"
    assert len(data["warnings"]) > 0
    assert any("no está activo" in w for w in data["warnings"])


def test_scheduler_health_degraded_when_no_jobs(client, mock_admin_key, mock_scheduler):
    """Verifica estado degraded cuando no hay jobs registrados."""
    mock_scheduler.get_jobs.return_value = []
    
    with patch("app.modules.admin.routes.scheduler_routes.get_scheduler", return_value=mock_scheduler):
        response = client.get(
            "/admin/scheduler/health",
            headers={"X-Admin-Key": mock_admin_key}
        )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] == "degraded"
    assert data["jobs_count"] == 0
    assert any("No hay jobs" in w for w in data["warnings"])


# Fin del archivo backend/tests/modules/admin/test_scheduler_routes.py
