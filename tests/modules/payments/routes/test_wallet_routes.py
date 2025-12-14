
# backend/tests/modules/payments/routes/test_wallet_routes.py
from http import HTTPStatus
import pytest


"""
Suite: Wallet Routes
Rutas objetivo:
  - GET /payments/wallet                       → obtener balance, reservado, disponible
  - GET /payments/wallet/ledger                → obtener transacciones de crédito/débito
  - POST /payments/wallet/recalculate          → forzar recálculo (opcional, admin/service)
Propósito:
  - Validar que el usuario autenticado recibe solo su wallet
  - Confirmar integridad de campos (balance, reserved, available)
  - Validar esquema de transacciones (ledger)
  - Confirmar comportamiento de recálculo
Requisitos:
  - Modelo principal: CreditWallet y CreditTransaction
  - Función SQL auxiliar: fn_wallet_get_breakdown
  - Fixture user_with_wallet crea wallet de prueba con balance > 0
"""


@pytest.mark.anyio
async def test_get_wallet_balance_ok(async_client, user_with_wallet, auth_headers):
    """
    GET /payments/wallet debe devolver balance del usuario autenticado.
    """
    headers = auth_headers(user_with_wallet["user_id"])
    r = await async_client.get("/payments/wallet", headers=headers)
    assert r.status_code == HTTPStatus.OK, r.text
    data = r.json()
    expected = {"user_id", "balance", "balance_reserved", "balance_available", "currency"}
    assert expected.issubset(data.keys())
    assert isinstance(data["balance"], (int, float))
    assert data["balance_available"] <= data["balance"]
    assert data["currency"] in ("mxn", "usd")


@pytest.mark.anyio
async def test_get_wallet_requires_auth(async_client):
    """
    Debe requerir autenticación.
    """
    r = await async_client.get("/payments/wallet")
    assert r.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.anyio
async def test_get_wallet_ledger_ok(async_client, user_with_wallet, auth_headers):
    """
    GET /payments/wallet/ledger devuelve lista de transacciones recientes.
    """
    headers = auth_headers(user_with_wallet["user_id"])
    r = await async_client.get("/payments/wallet/ledger", headers=headers)
    assert r.status_code == HTTPStatus.OK
    ledger = r.json()
    assert isinstance(ledger, list)
    if ledger:
        tx = ledger[0]
        expected = {"tx_id", "amount_cents", "type", "source_payment_id", "created_at"}
        assert expected.issubset(tx.keys())
        assert tx["type"] in ("purchase", "reservation", "reversal", "adjustment")


@pytest.mark.anyio
async def test_get_wallet_ledger_filters_by_type(async_client, user_with_wallet, auth_headers):
    """
    GET /payments/wallet/ledger?type=purchase debe devolver solo ese tipo.
    """
    headers = auth_headers(user_with_wallet["user_id"])
    r = await async_client.get("/payments/wallet/ledger?type=purchase", headers=headers)
    assert r.status_code == HTTPStatus.OK
    ledger = r.json()
    assert isinstance(ledger, list)
    for tx in ledger:
        assert tx["type"] == "purchase"


@pytest.mark.anyio
async def test_get_wallet_ledger_supports_pagination(async_client, user_with_wallet, auth_headers):
    """
    GET /payments/wallet/ledger?limit=N devuelve cantidad esperada.
    """
    headers = auth_headers(user_with_wallet["user_id"])
    r = await async_client.get("/payments/wallet/ledger?limit=5", headers=headers)
    assert r.status_code == HTTPStatus.OK
    ledger = r.json()
    assert isinstance(ledger, list)
    assert len(ledger) <= 5


# Endpoint /wallet/recalculate no implementado en v3 - tests eliminados


@pytest.mark.anyio
async def test_wallet_handles_missing_wallet(async_client, auth_headers):
    """
    Si el usuario no tiene wallet, debe devolver 404.
    """
    r = await async_client.get("/payments/wallet", headers=auth_headers(user_id=9999))
    assert r.status_code == HTTPStatus.NOT_FOUND


# Test de manejo de errores internos no aplicable en v3 - test eliminado

# Fin del archivo backend/tests/modules/payments/routes/test_wallet_routes.py