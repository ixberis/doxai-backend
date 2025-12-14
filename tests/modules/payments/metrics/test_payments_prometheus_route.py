
# -*- coding: utf-8 -*-
"""
Prueba del exportador Prometheus de Payments.

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""
import pytest
from httpx import AsyncClient, ASGITransport

pytestmark = pytest.mark.anyio


async def test_prometheus_export_ok(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/payments/metrics")
    
    # Debug: imprimir respuesta si falla
    if r.status_code != 200:
        print(f"\n[DEBUG] Status: {r.status_code}")
        print(f"[DEBUG] Headers: {r.headers}")
        print(f"[DEBUG] Body: {r.text[:500]}")
    
    assert r.status_code == 200
    # Content-Type de Prometheus
    assert "text/plain" in r.headers.get("content-type", "")
    # Debe contener al menos el nombre de alguna métrica registrada
    assert "payments_webhook_received_total" in r.text
