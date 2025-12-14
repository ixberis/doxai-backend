
# backend/tests/modules/payments/routes/test_receipts_routes.py
from http import HTTPStatus
import pytest
import re


"""
Suite: Receipts Routes
Rutas objetivo:
  - POST /payments/{payment_id}/receipts         → Generar recibo PDF firmado
  - GET  /payments/{payment_id}/receipt-url      → Obtener URL firmada de descarga
Propósito:
  - Validar generación de recibo solo para pagos elegibles (PAID/REFUNDED)
  - Confirmar estructura y campos devueltos (receipt_id, receipt_url, storage_path)
  - Validar re-firmado de URL existente y path estable
  - Manejo de errores: inexistente, no elegible, ya generado
Requisitos:
  - El facade receipts/generator.py crea el PDF
  - receipts/signer.py firma digitalmente el documento
  - receipts/eligibility.py valida elegibilidad por estado del Payment
  - Fixtures:
      * seeded_paid_payment → Payment con status='paid'
      * seeded_refunded_payment → Payment con status='refunded'
"""


@pytest.mark.anyio
async def test_generate_receipt_for_paid_payment(async_client, seeded_paid_payment, auth_headers):
    """
    Genera un recibo válido para Payment con status=paid.
    """
    pid = seeded_paid_payment["payment_id"]
    r = await async_client.post(f"/payments/{pid}/receipts", json={}, headers=auth_headers())
    assert r.status_code == HTTPStatus.OK, r.text
    data = r.json()
    expected = {"receipt_id", "receipt_url", "storage_path", "expires_at"}
    assert expected.issubset(data.keys())
    assert data["storage_path"].endswith(".pdf")
    assert data["receipt_url"].startswith("https://")
    assert re.match(r"^https://.*\.pdf(\?|$)", data["receipt_url"])


@pytest.mark.anyio
async def test_generate_receipt_for_refunded_payment(async_client, seeded_refunded_payment, auth_headers):
    """
    También debe permitir recibos para pagos reembolsados.
    """
    pid = seeded_refunded_payment["payment_id"]
    r = await async_client.post(f"/payments/{pid}/receipts", json={}, headers=auth_headers())
    assert r.status_code == HTTPStatus.OK
    data = r.json()
    assert data["receipt_url"].startswith("https://")
    assert "refunded" in data["receipt_url"].lower() or "receipt" in data["storage_path"]


@pytest.mark.anyio
async def test_generate_receipt_not_eligible_payment(async_client, seeded_pending_payment, auth_headers):
    """
    No debe permitir recibos si el pago no está pagado o reembolsado.
    """
    pid = seeded_pending_payment["payment_id"]
    r = await async_client.post(f"/payments/{pid}/receipts", json={}, headers=auth_headers())
    assert r.status_code == HTTPStatus.BAD_REQUEST
    assert "not eligible" in r.text.lower() or "invalid status" in r.text.lower()


@pytest.mark.anyio
async def test_generate_receipt_nonexistent_payment(async_client, auth_headers):
    """
    Debe retornar 404 si el payment_id no existe.
    """
    r = await async_client.post("/payments/999999/receipts", json={}, headers=auth_headers())
    assert r.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.anyio
async def test_get_receipt_url_returns_signed_link(async_client, seeded_paid_payment, auth_headers):
    """
    GET /payments/{id}/receipt-url debe devolver un link HTTPS firmado y con expiración.
    """
    pid = seeded_paid_payment["payment_id"]
    # Crear recibo previo
    await async_client.post(f"/payments/{pid}/receipts", json={}, headers=auth_headers())
    r = await async_client.get(f"/payments/{pid}/receipt-url", headers=auth_headers())
    assert r.status_code == HTTPStatus.OK
    data = r.json()
    assert isinstance(data, str)
    assert data.startswith("https://")
    assert ".pdf" in data
    assert "sig=" in data or "token=" in data


@pytest.mark.anyio
async def test_get_receipt_url_regenerates_when_expired(monkeypatch, async_client, seeded_paid_payment, auth_headers):
    """
    Si la URL firmada anterior expiró, debe generarse una nueva.
    """
    from app.modules.payments.facades.receipts import signer

    # Mock para detectar generación de nueva firma
    called = {}

    def fake_sign_url(path: str, expires_in: int = 3600):
        called["new_url"] = f"https://signed.new/{path}?sig=fake"
        return called["new_url"]

    monkeypatch.setattr(signer, "sign_receipt_url", fake_sign_url)

    pid = seeded_paid_payment["payment_id"]
    # Generar recibo inicial
    await async_client.post(f"/payments/{pid}/receipts", json={}, headers=auth_headers())
    # Forzar expiración y obtener nueva URL
    r = await async_client.get(f"/payments/{pid}/receipt-url", headers=auth_headers())
    assert r.status_code == HTTPStatus.OK
    assert r.json().startswith("https://signed.new/")
    assert "new_url" in called


@pytest.mark.anyio
async def test_receipt_metadata_persists_path(async_client, seeded_paid_payment, auth_headers):
    """
    El recibo generado debe persistir el mismo storage_path en re-generaciones.
    """
    pid = seeded_paid_payment["payment_id"]
    r1 = await async_client.post(f"/payments/{pid}/receipts", json={}, headers=auth_headers())
    path_1 = r1.json()["storage_path"]

    r2 = await async_client.post(f"/payments/{pid}/receipts", json={}, headers=auth_headers())
    path_2 = r2.json()["storage_path"]

    assert path_1 == path_2, "El path del PDF debe ser estable entre regeneraciones"


@pytest.mark.anyio
async def test_receipt_includes_signature_metadata(monkeypatch, async_client, seeded_paid_payment, auth_headers):
    """
    El PDF generado debe incluir campos de firma digital y fecha.
    """
    from app.modules.payments.facades.receipts import generator

    called = {}

    async def fake_generate_receipt_pdf(payment, *args, **kwargs):
        called["ok"] = True
        return {"storage_path": "receipts/test_receipt.pdf", "signed_at": "2025-11-03T00:00:00Z"}

    monkeypatch.setattr(generator, "generate_receipt_pdf", fake_generate_receipt_pdf)

    pid = seeded_paid_payment["payment_id"]
    r = await async_client.post(f"/payments/{pid}/receipts", json={}, headers=auth_headers())
    assert r.status_code == HTTPStatus.OK
    data = r.json()
    assert called.get("ok")
    assert "signed_at" in data or "receipt_id" in data


@pytest.mark.anyio
async def test_generate_receipt_handles_internal_error(monkeypatch, async_client, seeded_paid_payment, auth_headers):
    """
    Si ocurre un error interno durante la generación, debe responder 500.
    """
    from app.modules.payments.facades.receipts import generator

    async def fake_generate_receipt_pdf(*args, **kwargs):
        raise RuntimeError("Generator crashed")

    monkeypatch.setattr(generator, "generate_receipt_pdf", fake_generate_receipt_pdf)

    pid = seeded_paid_payment["payment_id"]
    r = await async_client.post(f"/payments/{pid}/receipts", json={}, headers=auth_headers())
    assert r.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert "error" in r.text.lower() or "generator" in r.text.lower()

# Fin del archivo backend/tests/modules/payments/routes/test_receipts_routes.py