
# backend/tests/modules/payments/routes/test_refunds_routes.py
from http import HTTPStatus
import pytest


"""
Suite: Refunds Routes
Rutas objetivo:
  - POST /payments/{payment_id}/refunds
  - GET  /payments/{payment_id}/refunds (historial)
Propósito:
  - Validar reembolso total y parcial
  - Confirmar idempotencia por idempotency_key
  - Rechazo para estados no elegibles (p. ej. pending, failed)
  - Validar estructura de respuesta coherente con refund_schemas
  - Confirmar actualización de Payment.status y reversa de créditos
Requisitos:
  - El facade payments/refunds.py orquesta el flujo de refund
  - Usa adaptadores según provider (Stripe, PayPal, interno)
  - refund.amount_cents puede ser None → reembolso total
  - refund.status ∈ {'pending', 'succeeded', 'failed', 'refunded'}
  - Fixture seeded_paid_payment crea un Payment elegible para reembolso
"""


@pytest.mark.anyio
async def test_refund_full_success(async_client, seeded_paid_payment, auth_headers):
    """
    Reembolso total: amount_cents=None, status debe pasar a refunded/pending según stub.
    """
    payment_id = seeded_paid_payment["payment_id"]
    payload = {"amount_cents": None, "reason": "requested_by_user"}
    r = await async_client.post(f"/payments/{payment_id}/refunds", json=payload, headers=auth_headers())
    assert r.status_code == HTTPStatus.OK, r.text
    data = r.json()
    assert "refund" in data
    refund = data["refund"]
    assert refund["payment_id"] == payment_id
    assert refund["amount_cents"] <= seeded_paid_payment["amount_cents"]
    assert refund["status"] in {"pending", "succeeded", "refunded"}
    # El Payment debe reflejarse en estado refunded/pending
    assert "payment" in data
    assert data["payment"]["status"] in {"refunded", "pending"}


@pytest.mark.anyio
async def test_refund_partial_success(async_client, seeded_paid_payment, auth_headers):
    """
    Reembolso parcial: amount_cents < total, estado intermedio pending/refunded.
    """
    payment_id = seeded_paid_payment["payment_id"]
    payload = {"amount_cents": seeded_paid_payment["amount_cents"] // 2, "reason": "partial_refund_test"}
    r = await async_client.post(f"/payments/{payment_id}/refunds", json=payload, headers=auth_headers())
    assert r.status_code == HTTPStatus.OK
    data = r.json()
    assert data["refund"]["amount_cents"] == seeded_paid_payment["amount_cents"] // 2
    assert data["refund"]["status"] in {"pending", "succeeded"}


@pytest.mark.anyio
async def test_refund_idempotency_key(async_client, seeded_paid_payment, auth_headers):
    """
    Mismo idempotency_key debe devolver el mismo refund_id.
    """
    pid = seeded_paid_payment["payment_id"]
    idem_key = "refund-idem-1"
    body = {"amount_cents": None, "idempotency_key": idem_key, "reason": "test"}
    r1 = await async_client.post(f"/payments/{pid}/refunds", json=body, headers=auth_headers())
    r2 = await async_client.post(f"/payments/{pid}/refunds", json=body, headers=auth_headers())
    assert r1.status_code == r2.status_code == HTTPStatus.OK
    d1, d2 = r1.json(), r2.json()
    assert d1["refund"]["refund_id"] == d2["refund"]["refund_id"]


@pytest.mark.anyio
async def test_refund_rejects_invalid_amount(async_client, seeded_paid_payment, auth_headers):
    """
    amount_cents <= 0 o mayor al pago deben generar 422.
    """
    pid = seeded_paid_payment["payment_id"]
    bad_payloads = [
        {"amount_cents": 0, "reason": "zero"},
        {"amount_cents": -100, "reason": "negative"},
        {"amount_cents": seeded_paid_payment["amount_cents"] * 2, "reason": "too_much"},
    ]
    for bad in bad_payloads:
        r = await async_client.post(f"/payments/{pid}/refunds", json=bad, headers=auth_headers())
        assert r.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.anyio
async def test_refund_rejects_nonexistent_payment(async_client, auth_headers):
    """
    Payment inexistente debe devolver 404.
    """
    r = await async_client.post("/payments/999999/refunds", json={"amount_cents": 100}, headers=auth_headers())
    assert r.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.anyio
async def test_refund_rejects_unpaid_payment(async_client, seeded_pending_payment, auth_headers):
    """
    Pagos con estado pending/no_paid no son elegibles para reembolso.
    """
    pid = seeded_pending_payment["payment_id"]
    r = await async_client.post(f"/payments/{pid}/refunds", json={"amount_cents": 100}, headers=auth_headers())
    assert r.status_code == HTTPStatus.BAD_REQUEST
    assert "not eligible" in r.text.lower() or "invalid status" in r.text.lower()


@pytest.mark.anyio
async def test_refund_double_refund_not_allowed(async_client, seeded_refunded_payment, auth_headers):
    """
    Payment ya reembolsado no puede reembolsarse de nuevo.
    """
    pid = seeded_refunded_payment["payment_id"]
    r = await async_client.post(f"/payments/{pid}/refunds", json={"amount_cents": 100}, headers=auth_headers())
    assert r.status_code == HTTPStatus.BAD_REQUEST
    assert "already refunded" in r.text.lower() or "not eligible" in r.text.lower()


@pytest.mark.anyio
async def test_refund_records_credit_reversal(async_client, seeded_paid_payment, auth_headers):
    """
    Un reembolso exitoso debe registrar reversal de créditos (CreditTransaction con tipo 'reversal').
    """
    pid = seeded_paid_payment["payment_id"]
    r = await async_client.post(f"/payments/{pid}/refunds", json={"amount_cents": 100}, headers=auth_headers())
    assert r.status_code == HTTPStatus.OK, r.text
    body = r.json()
    assert "credit_reversal" in body
    reversal = body["credit_reversal"]
    assert reversal["type"] == "reversal"
    assert reversal["amount_cents"] == 100
    assert reversal["user_id"] == seeded_paid_payment["user_id"]


@pytest.mark.anyio
async def test_list_refunds_for_payment(async_client, seeded_paid_payment, auth_headers):
    """
    GET /payments/{payment_id}/refunds debe listar todos los reembolsos asociados.
    """
    pid = seeded_paid_payment["payment_id"]
    # Crear dos reembolsos parciales
    for amt in (100, 200):
        await async_client.post(f"/payments/{pid}/refunds", json={"amount_cents": amt}, headers=auth_headers())

    r = await async_client.get(f"/payments/{pid}/refunds", headers=auth_headers())
    assert r.status_code == HTTPStatus.OK
    items = r.json()
    assert isinstance(items, list)
    assert all(rf["payment_id"] == pid for rf in items)
    amounts = [rf["amount_cents"] for rf in items]
    assert 100 in amounts and 200 in amounts


@pytest.mark.anyio
async def test_refund_handles_provider_failure(monkeypatch, async_client, seeded_paid_payment, auth_headers):
    """
    Si el proveedor devuelve error (p. ej. red/servicio), el refund debe marcarse failed.
    """
    from app.modules.payments.facades.payments import refunds

    async def fake_provider_failure(*args, **kwargs):
        raise RuntimeError("Provider API failure")

    # Mockear la función auxiliar que el stub llama
    monkeypatch.setattr(refunds, "refund_via_provider", fake_provider_failure)

    pid = seeded_paid_payment["payment_id"]
    r = await async_client.post(f"/payments/{pid}/refunds", json={"amount_cents": 100}, headers=auth_headers())
    assert r.status_code == HTTPStatus.BAD_GATEWAY
    data = r.json()
    assert "provider" in data["detail"].lower() and "failure" in data["detail"].lower()

# Fin del archivo backend/tests/modules/payments/routes/test_refunds_routes.py