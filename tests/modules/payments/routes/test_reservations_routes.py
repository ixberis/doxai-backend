
# backend/tests/modules/payments/routes/test_reservations_routes.py
from http import HTTPStatus
import pytest


"""
Suite: Reservations Routes
Rutas objetivo:
  - POST /payments/reservations                → crear reserva de créditos
  - POST /payments/reservations/{id}/consume   → consumir créditos reservados
  - POST /payments/reservations/{id}/release   → liberar créditos no usados
Propósito:
  - Validar creación, consumo y liberación de créditos reservados
  - Confirmar manejo de estados reservation_status (created, consumed, released, expired)
  - Validar restricciones: no sobreconsumir, no liberar ya consumidos
  - Confirmar idempotencia por idempotency_key
Requisitos:
  - Modelo: UsageReservation
  - Servicio: reservation_service
  - SQL helper: fn_reservation_create, fn_reservation_consume, fn_reservation_release
  - Fixture user_with_wallet crea wallet con balance >= credits solicitados
"""


@pytest.mark.anyio
async def test_create_reservation_happy_path(async_client, user_with_wallet, auth_headers):
    """
    Crear reserva válida con créditos suficientes.
    """
    headers = auth_headers(user_with_wallet["user_id"])
    payload = {"credits": 10, "operation_code": "job_run", "idempotency_key": "idem1"}
    r = await async_client.post("/payments/reservations", json=payload, headers=headers)
    assert r.status_code == HTTPStatus.OK, r.text
    data = r.json()
    expected = {"reservation_id", "user_id", "credits", "status", "created_at"}
    assert expected.issubset(data.keys())
    assert data["status"] == "created"
    assert data["credits"] == 10
    assert data["user_id"] == user_with_wallet["user_id"]


@pytest.mark.anyio
async def test_create_reservation_insufficient_balance(async_client, low_balance_wallet, auth_headers):
    """
    Si el usuario no tiene saldo suficiente, debe rechazar con 400.
    """
    headers = auth_headers(low_balance_wallet["user_id"])
    payload = {"credits": 9999, "operation_code": "job_run"}
    r = await async_client.post("/payments/reservations", json=payload, headers=headers)
    assert r.status_code == HTTPStatus.BAD_REQUEST
    assert "insufficient" in r.text.lower() or "balance" in r.text.lower()


@pytest.mark.anyio
async def test_create_reservation_invalid_payload(async_client, user_with_wallet, auth_headers):
    """
    credits <= 0 o sin operation_code → 422.
    """
    headers = auth_headers(user_with_wallet["user_id"])
    bad_payloads = [
        {"credits": 0, "operation_code": "op"},
        {"credits": -1, "operation_code": "op"},
        {"credits": 5},
    ]
    for bad in bad_payloads:
        r = await async_client.post("/payments/reservations", json=bad, headers=headers)
        assert r.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.anyio
async def test_reservation_idempotency(async_client, user_with_wallet, auth_headers):
    """
    Misma idempotency_key debe devolver misma reserva.
    """
    headers = auth_headers(user_with_wallet["user_id"])
    payload = {"credits": 5, "operation_code": "op_test", "idempotency_key": "same-key"}
    r1 = await async_client.post("/payments/reservations", json=payload, headers=headers)
    r2 = await async_client.post("/payments/reservations", json=payload, headers=headers)
    assert r1.status_code == r2.status_code == HTTPStatus.OK
    assert r1.json()["reservation_id"] == r2.json()["reservation_id"]


@pytest.mark.anyio
async def test_consume_reservation_ok(async_client, seeded_reservation, auth_headers):
    """
    Consumir créditos de reserva creada.
    """
    rid = seeded_reservation["reservation_id"]
    headers = auth_headers(seeded_reservation["user_id"])
    body = {"credits": seeded_reservation["credits"]}
    r = await async_client.post(f"/payments/reservations/{rid}/consume", json=body, headers=headers)
    assert r.status_code == HTTPStatus.OK
    data = r.json()
    assert data["status"] == "consumed"
    assert data["credits_consumed"] == seeded_reservation["credits"]


@pytest.mark.anyio
async def test_consume_reservation_overconsume(async_client, seeded_reservation, auth_headers):
    """
    No debe permitir consumir más créditos que los reservados.
    """
    rid = seeded_reservation["reservation_id"]
    headers = auth_headers(seeded_reservation["user_id"])
    body = {"credits": seeded_reservation["credits"] + 10}
    r = await async_client.post(f"/payments/reservations/{rid}/consume", json=body, headers=headers)
    assert r.status_code == HTTPStatus.BAD_REQUEST
    assert "exceed" in r.text.lower() or "invalid" in r.text.lower()


@pytest.mark.anyio
async def test_consume_nonexistent_reservation(async_client, auth_headers):
    """
    Reserva inexistente → 404.
    """
    r = await async_client.post("/payments/reservations/99999/consume", json={"credits": 5}, headers=auth_headers())
    assert r.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.anyio
async def test_release_reservation_ok(async_client, seeded_reservation, auth_headers):
    """
    Liberar reserva creada.
    """
    rid = seeded_reservation["reservation_id"]
    headers = auth_headers(seeded_reservation["user_id"])
    r = await async_client.post(f"/payments/reservations/{rid}/release", headers=headers)
    assert r.status_code == HTTPStatus.OK
    data = r.json()
    assert data["status"] == "released"


@pytest.mark.anyio
async def test_release_reservation_already_consumed(async_client, consumed_reservation, auth_headers):
    """
    No puede liberar una reserva ya consumida.
    """
    rid = consumed_reservation["reservation_id"]
    headers = auth_headers(consumed_reservation["user_id"])
    r = await async_client.post(f"/payments/reservations/{rid}/release", headers=headers)
    assert r.status_code == HTTPStatus.BAD_REQUEST
    assert "consumed" in r.text.lower() or "invalid" in r.text.lower()


@pytest.mark.anyio
async def test_expired_reservation_rejected(async_client, expired_reservation, auth_headers):
    """
    Intentar consumir o liberar una reserva expirada debe retornar 400.
    """
    rid = expired_reservation["reservation_id"]
    headers = auth_headers(expired_reservation["user_id"])
    r1 = await async_client.post(f"/payments/reservations/{rid}/consume", json={"credits": 1}, headers=headers)
    r2 = await async_client.post(f"/payments/reservations/{rid}/release", headers=headers)
    assert r1.status_code == r2.status_code == HTTPStatus.BAD_REQUEST
    assert "expired" in (r1.text.lower() + r2.text.lower())


@pytest.mark.anyio
async def test_reservation_list_for_user(async_client, user_with_wallet, auth_headers):
    """
    GET /payments/reservations lista todas las reservas del usuario.
    """
    headers = auth_headers(user_with_wallet["user_id"])
    r = await async_client.get("/payments/reservations", headers=headers)
    
    # DEBUG: Imprimir detalles del error si falla
    if r.status_code != HTTPStatus.OK:
        print(f"\n=== ERROR DEBUG ===")
        print(f"Status: {r.status_code}")
        print(f"Headers sent: {headers}")
        print(f"Response: {r.text}")
        print(f"==================\n")
    
    assert r.status_code == HTTPStatus.OK
    items = r.json()
    assert isinstance(items, list)
    for res in items:
        assert res["user_id"] == user_with_wallet["user_id"]
        assert res["status"] in {"created", "consumed", "released", "expired"}


@pytest.mark.anyio
async def test_reservation_internal_error(monkeypatch, async_client, user_with_wallet, auth_headers):
    """
    Simula error interno al crear reserva.
    """
    from app.modules.payments.routes import _stubs_tests_routes

    # Inyectar error usando el hook de testing
    _stubs_tests_routes.create_reservation._test_error = RuntimeError("Database failure")

    headers = auth_headers(user_with_wallet["user_id"])
    r = await async_client.post(
        "/payments/reservations", 
        json={"credits": 5, "operation_code": "test"},
        headers=headers
    )
    
    # Limpiar el hook después del test
    _stubs_tests_routes.create_reservation._test_error = None
    
    assert r.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert "failure" in r.text.lower() or "error" in r.text.lower()

# Fin del archivo backend/tests/modules/payments/routes/test_reservations_routes.py