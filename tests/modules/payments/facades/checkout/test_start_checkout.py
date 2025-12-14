
# backend/tests/modules/payments/facades/checkout/test_start_checkout.py
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import importlib

from app.modules.payments.facades.checkout import start_checkout
from app.modules.payments.facades.checkout.dto import ProviderCheckoutInfo
from app.modules.payments.enums import PaymentProvider, Currency, PaymentStatus


@pytest.mark.asyncio
async def test_start_checkout_happy_path_stripe(monkeypatch, db):
    """
    Test del happy path de start_checkout con Stripe.
    Mockea create_provider_checkout_session y PaymentService.create_payment.
    """
    # Mock de create_provider_checkout_session (la función real que usa start_checkout)
    fake_provider_info = ProviderCheckoutInfo(
        provider_session_id="cs_test_123",
        redirect_url=None,
        client_secret="pi_test_123_secret_fake",
    )
    
    async def fake_create_provider_checkout_session(**kwargs):
        return fake_provider_info
    
    # Parchear donde start_checkout importó la función (namespace del módulo real)
    start_checkout_mod = importlib.import_module(
        "app.modules.payments.facades.checkout.start_checkout"
    )
    monkeypatch.setattr(
        start_checkout_mod,
        "create_provider_checkout_session",
        fake_create_provider_checkout_session,
    )
    
    # Mock del PaymentService.create_payment
    fake_payment = MagicMock()
    fake_payment.id = 555
    fake_payment.user_id = "7"
    fake_payment.provider = PaymentProvider.STRIPE
    fake_payment.currency = Currency.USD
    fake_payment.amount = Decimal("150.00")
    fake_payment.credits_awarded = 150
    fake_payment.status = PaymentStatus.CREATED
    fake_payment.payment_intent_id = None
    fake_payment.idempotency_key = "test-idem-key"
    fake_payment.metadata_json = {}
    
    payment_service = AsyncMock()
    payment_service.create_payment = AsyncMock(return_value=fake_payment)
    
    # Preparar payload
    from app.modules.payments.facades.checkout.dto import CheckoutRequest
    
    payload = CheckoutRequest(
        provider=PaymentProvider.STRIPE,
        amount=Decimal("150.00"),
        currency=Currency.USD,
        credits=150,
        success_url="https://app.example.com/success",
        cancel_url="https://app.example.com/cancel",
    )
    
    # Ejecutar start_checkout
    result = await start_checkout(
        db,
        user_id="7",
        payload=payload,
        payment_service=payment_service,
    )
    
    # Verificaciones
    assert result.payment_id == 555
    assert result.provider == PaymentProvider.STRIPE
    assert result.provider_info.provider_session_id == "cs_test_123"
    assert result.provider_info.client_secret == "pi_test_123_secret_fake"
    assert result.provider_info.redirect_url is None
    
    # Verificar que se llamó a create_payment con los parámetros correctos
    payment_service.create_payment.assert_awaited_once()
    call_kwargs = payment_service.create_payment.call_args.kwargs
    assert call_kwargs["user_id"] == "7"
    assert call_kwargs["provider"] == PaymentProvider.STRIPE
    assert call_kwargs["currency"] == Currency.USD
    assert call_kwargs["amount"] == Decimal("150.00")
    assert call_kwargs["credits_awarded"] == 150


@pytest.mark.asyncio
async def test_start_checkout_happy_path_paypal(monkeypatch, db):
    """
    Test del happy path de start_checkout con PayPal.
    """
    # Mock de create_provider_checkout_session para PayPal
    fake_provider_info = ProviderCheckoutInfo(
        provider_session_id="paypal_order_555",
        redirect_url="https://paypal.example/checkout?payment_id=555",
        client_secret=None,
    )
    
    async def fake_create_provider_checkout_session(**kwargs):
        return fake_provider_info
    
    # Parchear donde start_checkout importó la función (namespace del módulo real)
    start_checkout_mod = importlib.import_module(
        "app.modules.payments.facades.checkout.start_checkout"
    )
    monkeypatch.setattr(
        start_checkout_mod,
        "create_provider_checkout_session",
        fake_create_provider_checkout_session,
    )
    
    # Mock del PaymentService
    fake_payment = MagicMock()
    fake_payment.id = 555
    fake_payment.user_id = "7"
    fake_payment.provider = PaymentProvider.PAYPAL
    fake_payment.currency = Currency.USD
    fake_payment.amount = Decimal("100.00")
    fake_payment.credits_awarded = 100
    fake_payment.status = PaymentStatus.CREATED
    fake_payment.payment_intent_id = None
    fake_payment.metadata_json = {}
    
    payment_service = AsyncMock()
    payment_service.create_payment = AsyncMock(return_value=fake_payment)
    
    from app.modules.payments.facades.checkout.dto import CheckoutRequest
    
    payload = CheckoutRequest(
        provider=PaymentProvider.PAYPAL,
        amount=Decimal("100.00"),
        currency=Currency.USD,
        credits=100,
        success_url="https://app.example.com/success",
        cancel_url="https://app.example.com/cancel",
    )
    
    result = await start_checkout(
        db,
        user_id="7",
        payload=payload,
        payment_service=payment_service,
    )
    
    assert result.payment_id == 555
    assert result.provider == PaymentProvider.PAYPAL
    assert result.provider_info.provider_session_id == "paypal_order_555"
    assert result.provider_info.redirect_url == "https://paypal.example/checkout?payment_id=555"
    assert result.provider_info.client_secret is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "amount,credits,success,cancel,err",
    [
        (0, 100, "http://u.com", "http://v.com", "amount"),
        (1, 0, "http://u.com", "http://v.com", "credits"),
        (100, 10, "not-a-valid-url", "http://v.com", "success_url"),
        (100, 10, "http://u.com", "also-invalid", "cancel_url"),
    ],
)
async def test_start_checkout_validation_errors(db, amount, credits, success, cancel, err):
    """
    Test de validaciones de Pydantic en CheckoutRequest.
    """
    from app.modules.payments.facades.checkout.dto import CheckoutRequest
    from pydantic import ValidationError
    
    # Intentar crear el CheckoutRequest con datos inválidos debería fallar en validación Pydantic
    with pytest.raises(ValidationError):
        payload = CheckoutRequest(
            provider=PaymentProvider.PAYPAL,
            amount=Decimal(str(amount)),
            currency=Currency.USD,
            credits=credits,
            success_url=success,
            cancel_url=cancel,
        )

# Fin del archivo backend/tests/modules/payments/facades/checkout/test_start_checkout.py
