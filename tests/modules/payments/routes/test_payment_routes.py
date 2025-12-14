
# backend/tests/modules/payments/routes/test_payments_routes.py
import uuid
from http import HTTPStatus

import pytest


"""
Suite: Payments Routes
Rutas objetivo:
  - GET /payments (listar pagos del usuario autenticado)
  - POST /payments/intents (crear o recuperar intención de pago desde proveedor)
  - GET /payments/{payment_id} (detalle)
  - DELETE /payments/{payment_id} (si existiera, cancelar)
Propósito:
  - Verificar creación idempotente de PaymentIntent (provider, provider_payment_id)
  - Confirmar validaciones (monto, currency, provider)
  - Confirmar que los endpoints listan solo pagos del usuario autenticado
  - Validar formato de respuesta coherente con payment_schemas
Requisitos previos:
  - Los modelos/enums y fachada PaymentService están stubbeados en modo test.
  - Fixture auth_headers simula usuario autenticado.
"""


@pytest.mark.anyio
async def test_create_payment_intent_happy_path(async_client, auth_headers):
    """
    Debe crear una intención de pago válida y devolver un payment_id único.
    """
    body = {
        "provider": "stripe",
        "provider_payment_id": f"pi_{uuid.uuid4()}",
        "amount_cents": 9900,
        "currency": "mxn",
        "credits_purchased": 600,
    }
    r = await async_client.post("/payments/intents", json=body, headers=auth_headers())
    assert r.status_code == HTTPStatus.OK, r.text
    data = r.json()
    expected = {
        "payment_id",
        "provider",
        "provider_payment_id",
        "amount_cents",
        "currency",
        "credits_purchased",
        "status",
    }
    assert expected.issubset(data.keys())
    assert data["amount_cents"] == 9900
    assert data["currency"] == "mxn"
    assert data["status"] in ("pending", "created", "requires_confirmation")


@pytest.mark.anyio
async def test_create_payment_intent_idempotent(async_client, auth_headers):
    """
    Misma combinación provider+provider_payment_id debe devolver el mismo payment_id.
    """
    base = {
        "provider": "stripe",
        "provider_payment_id": "cs_test_same",
        "amount_cents": 10000,
        "currency": "mxn",
        "credits_purchased": 800,
    }
    r1 = await async_client.post("/payments/intents", json=base, headers=auth_headers())
    r2 = await async_client.post("/payments/intents", json=base, headers=auth_headers())
    assert r1.status_code == r2.status_code == HTTPStatus.OK, (r1.text, r2.text)
    assert r1.json()["payment_id"] == r2.json()["payment_id"]
    assert r1.json()["provider_payment_id"] == "cs_test_same"


@pytest.mark.anyio
async def test_create_payment_intent_invalid_values(async_client, auth_headers):
    """
    amount_cents > 0, credits_purchased > 0, provider válido, provider_payment_id no vacío.
    """
    bad_payloads = [
        {"provider": "stripe", "provider_payment_id": "", "amount_cents": 200, "currency": "mxn", "credits_purchased": 10},
        {"provider": "stripe", "provider_payment_id": "ok", "amount_cents": 0, "currency": "mxn", "credits_purchased": 10},
        {"provider": "stripe", "provider_payment_id": "ok", "amount_cents": -10, "currency": "mxn", "credits_purchased": 10},
        {"provider": "stripe", "provider_payment_id": "ok", "amount_cents": 100, "currency": "mxn", "credits_purchased": 0},
        {"provider": "unknownpay", "provider_payment_id": "ok", "amount_cents": 100, "currency": "mxn", "credits_purchased": 1},
    ]
    for bad in bad_payloads:
        r = await async_client.post("/payments/intents", json=bad, headers=auth_headers())
        assert r.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.anyio
async def test_list_payments_returns_only_user_payments(async_client, auth_headers):
    """
    GET /payments debe listar únicamente pagos del usuario autenticado.
    """
    # El fixture de pruebas debería crear algunos pagos para user_id=1 y otros para user_id=2.
    # En este test, autenticamos como user_id=1 y verificamos el filtrado.
    headers_user1 = auth_headers(user_id=1)
    headers_user2 = auth_headers(user_id=2)

    # Obtener pagos del usuario 1
    r1 = await async_client.get("/payments", headers=headers_user1)
    assert r1.status_code == HTTPStatus.OK
    payments1 = r1.json()
    assert isinstance(payments1, list)
    for p in payments1:
        assert p["user_id"] == 1

    # Obtener pagos del usuario 2
    r2 = await async_client.get("/payments", headers=headers_user2)
    assert r2.status_code == HTTPStatus.OK
    payments2 = r2.json()
    assert isinstance(payments2, list)
    for p in payments2:
        assert p["user_id"] == 2

    # No debe haber traslape de pagos entre usuarios distintos
    ids_user1 = {p["payment_id"] for p in payments1}
    ids_user2 = {p["payment_id"] for p in payments2}
    assert ids_user1.isdisjoint(ids_user2)


@pytest.mark.anyio
async def test_get_payment_detail_ok(async_client, seeded_paid_payment, auth_headers):
    """
    GET /payments/{id} debe retornar el detalle de un pago existente.
    """
    payment_id = seeded_paid_payment["payment_id"]
    r = await async_client.get(f"/payments/{payment_id}", headers=auth_headers())
    assert r.status_code == HTTPStatus.OK
    data = r.json()
    expected = {
        "payment_id",
        "provider",
        "amount_cents",
        "currency",
        "credits_purchased",
        "status",
        "created_at",
    }
    assert expected.issubset(data.keys())
    assert data["payment_id"] == payment_id


@pytest.mark.anyio
async def test_get_payment_detail_not_found(async_client, auth_headers):
    """
    GET /payments/{id} inexistente debe retornar 404.
    """
    r = await async_client.get("/payments/999999", headers=auth_headers())
    assert r.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.anyio
async def test_delete_payment_pending(async_client, seeded_pending_payment, auth_headers):
    """
    DELETE /payments/{id} debe permitir cancelar pagos en estado pending.
    """
    pid = seeded_pending_payment["payment_id"]
    r = await async_client.delete(f"/payments/{pid}", headers=auth_headers())
    assert r.status_code in (HTTPStatus.OK, HTTPStatus.NO_CONTENT)
    # Subsecuente GET debe devolver 404 o status cancelled
    r2 = await async_client.get(f"/payments/{pid}", headers=auth_headers())
    if r2.status_code == HTTPStatus.OK:
        assert r2.json()["status"] in ("cancelled", "voided")
    else:
        assert r2.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.anyio
async def test_delete_payment_non_pending_forbidden(async_client, seeded_paid_payment, auth_headers):
    """
    DELETE /payments/{id} con estado pagado debe rechazar (403).
    """
    pid = seeded_paid_payment["payment_id"]
    r = await async_client.delete(f"/payments/{pid}", headers=auth_headers())
    assert r.status_code == HTTPStatus.FORBIDDEN


@pytest.mark.anyio
async def test_list_payments_supports_filter_by_status(async_client, auth_headers):
    """
    GET /payments?status=paid debe devolver solo pagos con ese estado.
    """
    r = await async_client.get("/payments?status=paid", headers=auth_headers())
    assert r.status_code == HTTPStatus.OK
    payments = r.json()
    for p in payments:
        assert p["status"] == "paid"


@pytest.mark.anyio
async def test_list_payments_supports_pagination(async_client, auth_headers):
    """
    GET /payments?limit=N&offset=M devuelve cantidad esperada.
    """
    r = await async_client.get("/payments?limit=5", headers=auth_headers())
    assert r.status_code == HTTPStatus.OK
    data = r.json()
    assert isinstance(data, list)
    assert len(data) <= 5

# Fin del archivo backend/tests/modules/payments/routes/test_payments_routes.py