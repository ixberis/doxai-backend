
# backend/tests/modules/payments/routes/test_reconciliation_routes.py
from http import HTTPStatus
from datetime import datetime, timedelta, timezone
import pytest


"""
Suite: Reconciliation Routes
Rutas objetivo:
  - POST /payments/reconciliation/report
  - GET  /payments/reconciliation/summary (opcional)
Propósito:
  - Validar generación de reporte de conciliación por proveedor y rango de fechas
  - Confirmar estructura del reporte (summary, discrepancies, period)
  - Validar filtrado por proveedor y rango de fechas
  - Confirmar manejo de errores por rango inválido o proveedor desconocido
Requisitos:
  - Facade: reconciliation/report.py, rules.py, loaders.py
  - Soporta provider ∈ {"stripe","paypal"}
  - Usa reconciler de base de datos y archivo externo simulado (stub)
  - Debe responder 200 con estructura JSON consistente
"""


@pytest.mark.anyio
async def test_generate_reconciliation_report_stripe(async_client, auth_headers):
    """
    Genera reporte exitoso para Stripe, rango de 7 días.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "provider": "stripe",
        "start_date": (now - timedelta(days=7)).isoformat(),
        "end_date": now.isoformat(),
        "include_matched": True,
    }
    r = await async_client.post("/payments/reconciliation/report", json=payload, headers=auth_headers())
    assert r.status_code == HTTPStatus.OK, r.text
    rep = r.json()
    expected = {"summary", "discrepancies", "period", "provider"}
    assert expected.issubset(rep.keys())
    assert rep["provider"] == "stripe"
    assert isinstance(rep["discrepancies"], list)
    assert isinstance(rep["summary"], dict)
    assert "start_date" in rep["period"] and "end_date" in rep["period"]


@pytest.mark.anyio
async def test_generate_reconciliation_report_paypal(async_client, auth_headers):
    """
    Genera reporte exitoso para PayPal.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "provider": "paypal",
        "start_date": (now - timedelta(days=2)).isoformat(),
        "end_date": now.isoformat(),
        "include_matched": False,
    }
    r = await async_client.post("/payments/reconciliation/report", json=payload, headers=auth_headers())
    assert r.status_code == HTTPStatus.OK
    data = r.json()
    assert data["provider"] == "paypal"
    assert isinstance(data["discrepancies"], list)
    for d in data["discrepancies"]:
        assert "payment_id" in d and "status_db" in d and "status_provider" in d


@pytest.mark.anyio
async def test_reconciliation_rejects_invalid_provider(async_client, auth_headers):
    """
    Provider no soportado → 422.
    """
    now = datetime.now(timezone.utc)
    payload = {"provider": "unknown", "start_date": now.isoformat(), "end_date": now.isoformat()}
    r = await async_client.post("/payments/reconciliation/report", json=payload, headers=auth_headers())
    assert r.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "provider" in r.text.lower()


@pytest.mark.anyio
async def test_reconciliation_invalid_dates(async_client, auth_headers):
    """
    Si las fechas son inválidas o invertidas, debe devolver 422.
    """
    now = datetime.now(timezone.utc)
    payload = {"provider": "stripe", "start_date": now.isoformat(), "end_date": (now - timedelta(days=5)).isoformat()}
    r = await async_client.post("/payments/reconciliation/report", json=payload, headers=auth_headers())
    assert r.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "date" in r.text.lower() or "range" in r.text.lower()


@pytest.mark.anyio
async def test_reconciliation_empty_range(async_client, auth_headers):
    """
    Si el rango no arroja resultados, debe devolver lista vacía pero 200.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "provider": "stripe",
        "start_date": (now - timedelta(days=1)).isoformat(),
        "end_date": now.isoformat(),
    }
    r = await async_client.post("/payments/reconciliation/report", json=payload, headers=auth_headers())
    assert r.status_code == HTTPStatus.OK
    rep = r.json()
    assert isinstance(rep["discrepancies"], list)


@pytest.mark.anyio
async def test_reconciliation_internal_error(monkeypatch, async_client, auth_headers):
    """
    Simula fallo interno en reconciliador.
    """
    from app.modules.payments.facades.reconciliation import report

    async def fake_generate_report(*args, **kwargs):
        raise RuntimeError("Loader failure")

    monkeypatch.setattr(report, "generate_reconciliation_report", fake_generate_report)

    now = datetime.now(timezone.utc)
    payload = {
        "provider": "stripe",
        "start_date": (now - timedelta(days=3)).isoformat(),
        "end_date": now.isoformat(),
    }
    r = await async_client.post("/payments/reconciliation/report", json=payload, headers=auth_headers())
    assert r.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert "failure" in r.text.lower() or "error" in r.text.lower()


@pytest.mark.anyio
async def test_reconciliation_summary_endpoint(async_client, auth_headers):
    """
    GET /payments/reconciliation/summary debe devolver indicadores globales.
    """
    r = await async_client.get("/payments/reconciliation/summary", headers=auth_headers())
    assert r.status_code == HTTPStatus.OK
    data = r.json()
    expected = {"provider", "total_payments", "matched", "unmatched", "last_run"}
    assert expected.issubset(data.keys())
    assert data["provider"] in ("stripe", "paypal", "aggregate")

# Fin del archivo backend/tests/modules/payments/routes/test_reconciliation_routes.py