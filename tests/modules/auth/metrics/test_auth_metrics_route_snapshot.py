
# -*- coding: utf-8 -*-
"""
backend/tests/modules/auth/metrics/test_auth_metrics_route_snapshot.py

Prueba del endpoint interno JSON de métricas del módulo Auth:
`GET /_internal/auth/metrics/snapshot`

- Monta un FastAPI mínimo e incluye el router real de métricas.
- Monkeypatch de AuthPrometheusExporter para controlar la salida.
- Override de la dependencia get_db (el exporter falso no la usa).

Autor: Ixchel Beristain
Fecha: 08/11/2025
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI

from httpx import AsyncClient
import httpx
from httpx import ASGITransport

# Importamos el router real del módulo
import app.modules.auth.metrics.routes.metrics_routes as metrics_routes


class _FakeExporter:
    """Sustituye a AuthPrometheusExporter en el router para pruebas."""
    def __init__(self, db):
        self.db = db

    async def refresh_gauges(self):
        # Retorna estructura que el endpoint convierte a schema AuthMetricsSnapshot
        return {"active_sessions": 9, "activation_conversion_ratio": 42.5}


@pytest.mark.anyio
async def test_auth_metrics_snapshot_route_returns_expected_json(monkeypatch):
    # 1) Monkeypatch del exporter dentro del módulo
    monkeypatch.setattr(metrics_routes, "AuthPrometheusExporter", _FakeExporter)

    # 2) Construimos una app mínima e incluimos el router
    app = FastAPI()
    app.include_router(metrics_routes.router)

    # 3) Override de get_db si el endpoint lo pide (devolver None/objeto fake)
    async def _fake_db():
        yield None
    try:
        from app.shared.database.database import get_db
        app.dependency_overrides[get_db] = _fake_db
    except Exception:
        # Si no existe en este entorno de pruebas, no es necesario el override
        pass

    # 4) Llamada al endpoint
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/_internal/auth/metrics/snapshot")
        assert resp.status_code == 200
        data = resp.json()

    # 5) Verificaciones
    assert resp.status_code == 200
    data = resp.json()
    # Debe regresar el schema de snapshot (sin PII)
    assert set(data.keys()) == {"active_sessions", "activation_conversion_ratio"}
    assert data["active_sessions"] == 9
    assert data["activation_conversion_ratio"] == 42.5

# Fin del archivo backend/tests/modules/auth/metrics/test_auth_metrics_route_snapshot.py
