
# backend/tests/modules/payments/facades/receipts/test_receipts_generator.py
import pytest
from fastapi import HTTPException
from app.modules.payments.facades.receipts import generate_receipt, get_receipt_url
from app.modules.payments.enums import PaymentStatus

@pytest.mark.asyncio
async def test_generate_receipt_new_stub_upload_and_signed_url(monkeypatch, db, make_payment):
    # Payment elegible (SUCCEEDED) y sin recibo previo
    eligible = make_payment(status=PaymentStatus.SUCCEEDED, payment_metadata={})

    class FakePaymentRepo:
        async def get(self, db, payment_id): 
            return eligible

    # se usa dentro de receipts.generator
    monkeypatch.setattr(
        "app.modules.payments.facades.receipts.generator.PaymentRepository",
        lambda: FakePaymentRepo(),
    )

    data = await generate_receipt(db, payment_id=123, user_billing_info={"name":"Ixchel"})
    assert data["receipt_id"]
    assert data["storage_path"].endswith(".pdf")
    assert data["receipt_url"].startswith("https://storage.doxai.com/")
    assert data["already_existed"] is False

@pytest.mark.asyncio
async def test_generate_receipt_not_eligible_status(monkeypatch, db, make_payment):
    ineligible = make_payment(status=type("S", (), {"value": "pending"})())

    class FakePaymentRepo:
        async def get(self, db, payment_id): 
            return ineligible

    # se usa dentro de receipts.generator (no en el paquete receipts)
    monkeypatch.setattr(
        "app.modules.payments.facades.receipts.generator.PaymentRepository",
        lambda: FakePaymentRepo(),
    )

    with pytest.raises(HTTPException) as ex:
        await generate_receipt(db, payment_id=321)
    assert ex.value.status_code == 422
# Fin del archivo backend/tests/modules/payments/facades/receipts/test_receipts_generator.py
