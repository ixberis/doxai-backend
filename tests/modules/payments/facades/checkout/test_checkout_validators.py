


# backend/tests/modules/payments/facades/checkout/test_checkout_validators.py
import pytest
from fastapi import HTTPException
from app.modules.payments.enums import PaymentProvider, Currency  # usado solo en asserts si aplican
from app.modules.payments.facades.checkout.validators import validate_checkout_params

@pytest.mark.parametrize(
    "amount_cents,credits,success_url,cancel_url",
    [
        (19900, 100, "https://app.doxai.mx/pagos/ok", "http://localhost:3000/cancel"),
        (500, 10, "https://app.doxai.mx/ok", "https://app.doxai.mx/cancel"),
    ],
)
def test_validate_checkout_params_ok(amount_cents, credits, success_url, cancel_url, monkeypatch):
    monkeypatch.setenv("ALLOW_HTTP_LOCALHOST", "1")
    # La función de tu código valida montos/urls/credits; provider/currency no van aquí
    validate_checkout_params(
        amount_cents=amount_cents,
        credits_purchased=credits,
        success_url=success_url,
        cancel_url=cancel_url,
    )

@pytest.mark.parametrize("bad_amount", [0, -1, -100])
def test_validate_checkout_params_bad_amount(bad_amount):
    with pytest.raises(HTTPException) as exc:
        validate_checkout_params(
            amount_cents=bad_amount,
            credits_purchased=10,
            success_url="https://app.doxai.mx/ok",
            cancel_url="https://app.doxai.mx/cancel",
        )
    assert exc.value.status_code == 422
    assert "amount" in str(exc.value.detail).lower()

@pytest.mark.parametrize("bad_credits", [0, -1, -100])
def test_validate_checkout_params_bad_credits(bad_credits):
    with pytest.raises(HTTPException) as exc:
        validate_checkout_params(
            amount_cents=100,
            credits_purchased=bad_credits,
            success_url="https://app.doxai.mx/ok",
            cancel_url="https://app.doxai.mx/cancel",
        )
    assert exc.value.status_code == 422
    assert "credits" in str(exc.value.detail).lower()

@pytest.mark.parametrize(
    "s_url,c_url",
    [
        ("ftp://doxai.mx/ok", "https://app.doxai.mx/cancel"),
        ("//app.doxai.mx/ok", "https://app.doxai.mx/cancel"),
        ("https://app.doxai.mx/ok", "mailto:cancel@doxai.mx"),
        ("http://example.com/ok", "http://example.com/cancel"),
    ],
)
def test_validate_checkout_params_bad_urls(s_url, c_url):
    with pytest.raises(HTTPException) as exc:
        validate_checkout_params(
            amount_cents=100,
            credits_purchased=10,
            success_url=s_url,
            cancel_url=c_url,
        )
    assert exc.value.status_code == 422
    assert "url" in str(exc.value.detail).lower() or "https" in str(exc.value.detail).lower()

# Fin del archivo backend/tests/modules/payments/facades/checkout/test_checkout_validators.py