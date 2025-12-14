# -*- coding: utf-8 -*-
"""
Prueba del snapshot DESDE BD de Payments.

Mockea los aggregators DB para que no dependan de MVs reales.

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.anyio


async def test_snapshot_db_ok(app, monkeypatch):
    """
    Test del endpoint /payments/metrics/snapshot-db mockeando los aggregators.
    """
    # Mock de get_metrics_snapshot_from_db para retornar datos simulados
    mock_snapshot_data = {
        "range": {"since": "2025-01-01T00:00:00", "until": "2025-01-02T00:00:00"},
        "filters": {"provider": None, "currency": None},
        "payments": {
            "series": [{"day": "2025-01-01", "payments_total": 10, "payments_succeeded": 8}],
            "kpis": {"total": 10, "succeeded": 8, "failed": 2, "success_rate": 80.0, "amount_cents_succeeded": 50000},
        },
        "credits": {
            "series": [{"day": "2025-01-01", "credits_purchased": 100, "credits_consumed": 50}],
            "kpis": {"purchased": 100, "consumed": 50, "available": 50},
        },
        "refunds": {
            "series": [{"day": "2025-01-01", "refunds_total": 2, "amount_cents_refunded": 10000}],
            "kpis": {"total": 2, "amount_cents_refunded": 10000},
        },
        "balance": {"total_balance": 100000, "total_reserved": 20000, "total_available": 80000},
        "reconciliation": [],
    }
    
    # Parchear donde se USA (routes_snapshot_db), no donde se define
    monkeypatch.setattr(
        "app.modules.payments.metrics.routes.routes_snapshot_db.get_metrics_snapshot_from_db",
        AsyncMock(return_value=mock_snapshot_data)
    )
    
    from httpx import ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/payments/metrics/snapshot-db", params={"hours": 24})
    
    assert r.status_code == 200
    data = r.json()
    assert data.get("source") == "database"
    assert "snapshot" in data
    snap = data["snapshot"]
    assert "payments" in snap and "credits" in snap and "refunds" in snap
