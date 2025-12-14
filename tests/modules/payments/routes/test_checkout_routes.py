
# backend/tests/modules/payments/routes/test_checkout_routes.py
import uuid
from http import HTTPStatus

import pytest


"""
Suite: Checkout Routes
Rutas objetivo (convenciones del módulo):
  - POST /payments/checkout
Contratos (esperados por DTO/validators y fachada):
  - Campos mínimos en 200 OK: payment_id, provider, provider_payment_id, payment_url, idempotency_key
  - Validaciones:
      * amount_cents > 0
      * credits_purchased > 0
      * currency ∈ {mxn, usd, ...} (los enums del módulo)
      * success_url/cancel_url deben ser https:// (o localhost/http(s) en dev) y bien formadas
  - Idempotencia:
      * Reintentos con el mismo client_nonce (y mismo usuario/proveedor) deben devolver el mismo payment_id
Notas:
  - El test asume la existencia de fixtures:
      * async_client: AsyncClient de httpx integrado con la app FastAPI
      * auth_headers(user_id: Optional[int]) -> dict[str,str]
      * db_session: sesión de BD (si el endpoint la utiliza)
  - No dependemos de proveedores reales; el ruteador/fachada debe estar stubbeado en modo test.
"""


@pytest.mark.anyio
@pytest.mark.parametrize("provider", ["stripe", "paypal"])
async def test_checkout_happy_path_ok(async_client, auth_headers, provider):
    """
    Happy path para proveedores soportados: genera la sesión de pago
    y regresa campos clave del intent/checkout.
    """
    payload = {
        "provider": provider,
        "amount_cents": 19900,
        "currency": "mxn",
        "credits_purchased": 1200,
        "success_url": "https://app.doxai.test/pay/success",
        "cancel_url": "https://app.doxai.test/pay/cancel",
        "client_nonce": f"nonce-{uuid.uuid4()}",
        # metadata opcional que el backend podría propagar
        "metadata": {"project_id": "proj_123", "source": "unit-test"},
    }
    r = await async_client.post("/payments/checkout", json=payload, headers=auth_headers())
    assert r.status_code == HTTPStatus.OK, r.text
    data = r.json()

    # Llaves mínimas (contrato estable del checkout)
    expected = {
        "payment_id",
        "provider",
        "provider_payment_id",
        "payment_url",
        "idempotency_key",
        "amount_cents",
        "currency",
        "credits_purchased",
        "status",
    }
    assert expected.issubset(data.keys())
    assert data["provider"] == provider
    assert data["amount_cents"] == payload["amount_cents"]
    assert data["currency"] == payload["currency"]
    assert data["credits_purchased"] == payload["credits_purchased"]
    assert isinstance(data["payment_url"], str) and data["payment_url"].startswith("http")


@pytest.mark.anyio
async def test_checkout_validates_amount_and_credits(async_client, auth_headers):
    """
    amount_cents y credits_purchased deben ser > 0.
    """
    bad_payloads = [
        {
            "provider": "stripe",
            "amount_cents": 0,
            "currency": "mxn",
            "credits_purchased": 100,
            "success_url": "https://ok/s",
            "cancel_url": "https://ok/c",
        },
        {
            "provider": "stripe",
            "amount_cents": -1,
            "currency": "mxn",
            "credits_purchased": 100,
            "success_url": "https://ok/s",
            "cancel_url": "https://ok/c",
        },
        {
            "provider": "stripe",
            "amount_cents": 1000,
            "currency": "mxn",
            "credits_purchased": 0,
            "success_url": "https://ok/s",
            "cancel_url": "https://ok/c",
        },
        {
            "provider": "stripe",
            "amount_cents": 1000,
            "currency": "mxn",
            "credits_purchased": -5,
            "success_url": "https://ok/s",
            "cancel_url": "https://ok/c",
        },
    ]
    for bad in bad_payloads:
        r = await async_client.post("/payments/checkout", json=bad, headers=auth_headers())
        assert r.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, f"payload should fail: {bad}"


@pytest.mark.anyio
async def test_checkout_validates_currency(async_client, auth_headers):
    """
    currency debe pertenecer a los enums soportados (p. ej. 'mxn', 'usd').
    """
    bad = {
        "provider": "stripe",
        "amount_cents": 1500,
        "currency": "xxx",  # no soportada
        "credits_purchased": 100,
        "success_url": "https://ok/s",
        "cancel_url": "https://ok/c",
    }
    r = await async_client.post("/payments/checkout", json=bad, headers=auth_headers())
    assert r.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.anyio
async def test_checkout_validates_urls(async_client, auth_headers):
    """
    success_url/cancel_url deben ser https:// o localhost válidos.
    """
    invalid = {
        "provider": "stripe",
        "amount_cents": 5000,
        "currency": "mxn",
        "credits_purchased": 200,
        "success_url": "ftp://invalid",
        "cancel_url": "http://host-without-tls",
    }
    r1 = await async_client.post("/payments/checkout", json=invalid, headers=auth_headers())
    assert r1.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    # Caso válido con https
    valid = {
        **invalid,
        "success_url": "https://app/s",
        "cancel_url": "https://app/c",
    }
    r2 = await async_client.post("/payments/checkout", json=valid, headers=auth_headers())
    assert r2.status_code == HTTPStatus.OK, r2.text

    # Caso válido con localhost (útil en desarrollo)
    local = {
        **invalid,
        "success_url": "http://localhost:5173/s",
        "cancel_url": "http://127.0.0.1:3000/c",
    }
    r3 = await async_client.post("/payments/checkout", json=local, headers=auth_headers())
    assert r3.status_code in (HTTPStatus.OK, HTTPStatus.UNPROCESSABLE_ENTITY)


@pytest.mark.anyio
async def test_checkout_rejects_unknown_provider(async_client, auth_headers):
    """
    provider no soportado debe rechazar con 422.
    """
    payload = {
        "provider": "unknownpay",
        "amount_cents": 1000,
        "currency": "mxn",
        "credits_purchased": 100,
        "success_url": "https://ok/s",
        "cancel_url": "https://ok/c",
    }
    r = await async_client.post("/payments/checkout", json=payload, headers=auth_headers())
    assert r.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.anyio
async def test_checkout_idempotency_by_client_nonce(async_client, auth_headers):
    """
    Dos llamadas con el mismo client_nonce para el mismo usuario/proveedor
    deben retornar el mismo payment_id/idempotency_key.
    """
    nonce = f"nonce-{uuid.uuid4()}"
    base = {
        "provider": "stripe",
        "amount_cents": 2500,
        "currency": "mxn",
        "credits_purchased": 150,
        "success_url": "https://ok/s",
        "cancel_url": "https://ok/c",
        "client_nonce": nonce,
    }
    r1 = await async_client.post("/payments/checkout", json=base, headers=auth_headers())
    r2 = await async_client.post("/payments/checkout", json=base, headers=auth_headers())
    assert r1.status_code == r2.status_code == HTTPStatus.OK, (r1.text, r2.text)
    d1, d2 = r1.json(), r2.json()
    assert d1["payment_id"] == d2["payment_id"]
    assert d1["idempotency_key"] == d2["idempotency_key"]


@pytest.mark.anyio
async def test_checkout_changes_with_different_nonce(async_client, auth_headers):
    """
    Si cambia el client_nonce, aunque el resto del payload sea idéntico,
    debe generarse una nueva intención (nuevo payment_id).
    """
    payload_a = {
        "provider": "paypal",
        "amount_cents": 9900,
        "currency": "mxn",
        "credits_purchased": 600,
        "success_url": "https://ok/s",
        "cancel_url": "https://ok/c",
        "client_nonce": "nonce-A",
    }
    payload_b = {**payload_a, "client_nonce": "nonce-B"}

    r1 = await async_client.post("/payments/checkout", json=payload_a, headers=auth_headers())
    r2 = await async_client.post("/payments/checkout", json=payload_b, headers=auth_headers())
    assert r1.status_code == r2.status_code == HTTPStatus.OK, (r1.text, r2.text)
    assert r1.json()["payment_id"] != r2.json()["payment_id"]


@pytest.mark.anyio
async def test_checkout_echoes_metadata_when_supported(async_client, auth_headers):
    """
    Si se envía 'metadata', el backend podría reflejar parte de ella en la respuesta.
    No es obligatorio, pero si existe la llave, debe ser dict.
    """
    payload = {
        "provider": "stripe",
        "amount_cents": 10000,
        "currency": "mxn",
        "credits_purchased": 700,
        "success_url": "https://ok/s",
        "cancel_url": "https://ok/c",
        "client_nonce": f"nonce-{uuid.uuid4()}",
        "metadata": {"project_id": "proj_test", "note": "from-tests"},
    }
    r = await async_client.post("/payments/checkout", json=payload, headers=auth_headers())
    assert r.status_code == HTTPStatus.OK, r.text
    data = r.json()
    if "metadata" in data:
        assert isinstance(data["metadata"], dict)
        # Al menos uno de los campos propagados
        assert any(k in data["metadata"] for k in ("project_id", "note"))

# Fin del archivo backend/tests/modules/payments/routes/test_checkout_routes.py