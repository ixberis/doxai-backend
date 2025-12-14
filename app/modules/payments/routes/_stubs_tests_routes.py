
from __future__ import annotations
# backend/app/modules/payments/routes/_stubs_tests_routes.py
"""
STUBS de endpoints de Payments para pruebas de ruteadores.
Se activan al montarse desde app/routes.py cuando USE_PAYMENT_STUBS=true.

Implementa:
- POST /api/payments/checkout
- POST /api/payments/checkout/start   (mismo handler)
- POST /api/payments/intents (crear intenciones de pago)
- GET /api/payments (listar pagos del usuario)
- GET /api/payments/{payment_id} (detalle de pago)
- DELETE /api/payments/{payment_id} (cancelar pago)
- POST /api/payments/webhooks/stripe
- POST /api/payments/webhooks/paypal

Nota: app/routes.py clona automáticamente estos endpoints a /payments/* para tests.

Alineado con expectativas de tests:
• Stripe:
  - 401 SOLO si la firma (Stripe-Signature) contiene 'invalid' o 'bad'
  - 422 cuando falta 'type' en el JSON
  - para eventos:
      · success_types → {"payment_intent.succeeded","charge.succeeded","checkout.session.completed"}
         ⇒ 200, {"status":"ok","called":{"ok": <event_type>}}
      · failed_types  → {"payment_intent.payment_failed","charge.failed"}
         ⇒ 200, {"status":"ok","called":{"fail": <event_type>}}
      · otros         ⇒ 200, {"status":"ignored","handled_event": <event_type>}
  - en respuestas 200 incluimos además "result": {"provider":"stripe","status":"received","signature":...}
• PayPal:
  - 401 si falta firma en modo seguro; en modo inseguro acepta sin firma
  - 422 si falta event_type
  - 200 en válidos/desconocidos con {"ok":true,"status":"received"} en raíz y firma en result
• Checkout stub con validaciones básicas + idempotencia por client_nonce
• Intents stub con idempotencia por user_id + provider + provider_payment_id

Autor: Ixchel Beristain
Fecha: 05/11/2025
"""



import os
import re
import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, status, Body, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Router con prefix para evitar conflicts en mounting
router = APIRouter(prefix="/payments", tags=["Payments-Tests"])

# ===== Helpers de entorno dinámico =====
def _allow_insecure() -> bool:
    # leer en cada request (los tests cambian el env en runtime)
    return os.getenv("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", "false").lower() == "true"

def _allow_http_local() -> bool:
    return os.getenv("PAYMENTS_ALLOW_HTTP_LOCAL", "false").lower() == "true"

# ====== Checkout ======
class CheckoutRequest(BaseModel):
    provider: str
    amount_cents: int
    currency: str
    credits_purchased: int
    success_url: str
    cancel_url: str
    metadata: Optional[Dict[str, Any]] = None
    client_nonce: Optional[str] = None

class CheckoutResponse(BaseModel):
    payment_id: int
    provider: str
    provider_payment_id: str
    payment_url: str
    payment_status: str = "pending"
    amount_cents: int
    currency: str
    credits_purchased: int
    idempotency_key: str
    payment_url_expires_at: Optional[str] = None
    status: Optional[str] = None  # alias adicional para payment_status

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_IDEM: dict[str, Dict[str, Any]] = {}
_PAYMENTS: dict[int, list[Dict[str, Any]]] = {}  # user_id -> [payments]
_INTENTS: dict[str, Dict[str, Any]] = {}  # key -> intent data
_RECEIPTS: dict[int, Dict[str, Any]] = {}  # payment_id -> receipt data
_REFUNDS: dict[int, list[Dict[str, Any]]] = {}  # payment_id -> [refunds]
_REFUND_IDEM: dict[str, Dict[str, Any]] = {}  # idempotency_key -> refund

# Pre-poblar algunos pagos para fixtures
def _seed_test_payments(*, clear_refunds: bool = False):
    """Poblar pagos de prueba para fixtures seeded_paid_payment, seeded_refunded_payment y seeded_pending_payment"""
    from datetime import datetime, timezone, timedelta
    
    if 1 not in _PAYMENTS:
        _PAYMENTS[1] = []
    
    # Buscar y actualizar pagos existentes o agregarlos si no existen
    payment_10 = next((p for p in _PAYMENTS[1] if p["payment_id"] == 10), None)
    if payment_10:
        # Si se solicita limpieza (clear_refunds=True), restaurar completamente
        if clear_refunds:
            payment_10["status"] = "paid"
            payment_10["amount_cents"] = 9900
            _REFUNDS.pop(10, None)
        else:
            # Si NO se solicita limpieza, solo restaurar si está en estado final inconsistente
            total_refunded = sum(r["amount_cents"] for r in _REFUNDS.get(10, []))
            if payment_10["status"] == "refunded" or total_refunded >= 9900:
                payment_10["status"] = "paid"
                payment_10["amount_cents"] = 9900
                _REFUNDS.pop(10, None)
    else:
        _PAYMENTS[1].append({
            "payment_id": 10,
            "user_id": 1,
            "amount_cents": 9900,
            "currency": "mxn",
            "credits_purchased": 600,
            "status": "paid",
            "provider": "stripe",
            "provider_payment_id": "pi_test_10",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    
    # Limpiar refunds de pagos 11 y 12 si se solicita
    if clear_refunds:
        _REFUNDS.pop(11, None)
        _REFUNDS.pop(12, None)
    
    payment_11 = next((p for p in _PAYMENTS[1] if p["payment_id"] == 11), None)
    if not payment_11:
        _PAYMENTS[1].append({
            "payment_id": 11,
            "user_id": 1,
            "amount_cents": 9900,
            "currency": "mxn",
            "credits_purchased": 600,
            "status": "refunded",
            "provider": "paypal",
            "provider_payment_id": "pi_test_11",
            "created_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        })
    
    payment_12 = next((p for p in _PAYMENTS[1] if p["payment_id"] == 12), None)
    if not payment_12:
        _PAYMENTS[1].append({
            "payment_id": 12,
            "user_id": 1,
            "amount_cents": 5000,
            "currency": "mxn",
            "credits_purchased": 300,
            "status": "pending",
            "provider": "stripe",
            "provider_payment_id": "pi_test_12",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

_seed_test_payments()

def _validate_url(u: str) -> bool:
    if not u or not _URL_RE.match(u):
        return False
    if u.lower().startswith("http://") and not _allow_http_local():
        return False
    return True

def _validate_currency(cur: str) -> bool:
    return (cur or "").lower() in {"mxn", "usd"}

def _validate_provider(p: str) -> bool:
    return (p or "").lower() in {"stripe", "paypal"}

# ====== Payment Intents ======
class IntentRequest(BaseModel):
    provider: str
    provider_payment_id: str
    amount_cents: int
    currency: str
    credits_purchased: int
    metadata: Optional[Dict[str, Any]] = None

class IntentResponse(BaseModel):
    payment_id: int
    provider: str
    provider_payment_id: str
    amount_cents: int
    currency: str
    credits_purchased: int
    status: str = "pending"
    user_id: Optional[int] = None
    created_at: Optional[str] = None

@router.post("/intents", response_model=IntentResponse)
async def create_intent(
    req: IntentRequest, 
    request: Request,
    x_user_id: Optional[str] = Header(default=None, convert_underscores=False, alias="X-User-ID")
):
    # Validaciones
    if not _validate_provider(req.provider):
        raise HTTPException(status_code=422, detail="provider inválido")
    if not req.provider_payment_id or req.provider_payment_id.strip() == "":
        raise HTTPException(status_code=422, detail="provider_payment_id requerido")
    if req.amount_cents <= 0:
        raise HTTPException(status_code=422, detail="amount_cents debe ser > 0")
    if req.credits_purchased <= 0:
        raise HTTPException(status_code=422, detail="credits_purchased debe ser > 0")
    if not _validate_currency(req.currency):
        raise HTTPException(status_code=422, detail="currency inválida")
    
    # Obtener user_id del header
    user_id = int(x_user_id) if x_user_id else 1
    
    # Idempotencia por user_id + provider + provider_payment_id
    key = f"{user_id}::{req.provider.lower()}::{req.provider_payment_id}"
    if key in _INTENTS:
        return _INTENTS[key]
    
    payment_id = hash(key) % 1000000
    resp = {
        "payment_id": payment_id,
        "provider": req.provider.lower(),
        "provider_payment_id": req.provider_payment_id,
        "amount_cents": req.amount_cents,
        "currency": req.currency.lower(),
        "credits_purchased": req.credits_purchased,
        "status": "pending",
    }
    
    # Guardar en memoria
    _INTENTS[key] = resp
    if user_id not in _PAYMENTS:
        _PAYMENTS[user_id] = []
    _PAYMENTS[user_id].append({**resp, "user_id": user_id})
    
    return resp

@router.get("", response_model=list)
async def list_payments(
    request: Request,
    x_user_id: Optional[str] = Header(default=None, convert_underscores=False, alias="X-User-ID"),
    status: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
):
    # Obtener user_id del header
    user_id = int(x_user_id) if x_user_id else 1
    payments = _PAYMENTS.get(user_id, [])
    
    # Filtrar por status si se especifica
    if status:
        payments = [p for p in payments if p.get("status") == status]
    
    # Aplicar paginación
    if offset:
        payments = payments[offset:]
    if limit:
        payments = payments[:limit]
    
    return payments

# ============================================================
# RESERVATIONS (DEBE IR ANTES DE /{payment_id} PARA EVITAR CONFLICTOS)
# ============================================================

class ReservationRequest(BaseModel):
    credits: int
    operation_code: str
    idempotency_key: Optional[str] = None

class ReservationResponse(BaseModel):
    reservation_id: int
    user_id: int
    credits: int
    status: str
    created_at: str
    consumed_at: Optional[str] = None
    released_at: Optional[str] = None

@router.get("/reservations", response_model=list)
async def list_reservations(
    request: Request,
    x_user_id: Optional[str] = Header(default=None, convert_underscores=False, alias="X-User-ID"),
    status: Optional[str] = None,
    limit: Optional[int] = None,
):
    """Lista todas las reservaciones del usuario."""
    user_id = int(x_user_id) if x_user_id else 1
    
    # Filtrar reservaciones por usuario
    user_reservations = [
        res for res in _RESERVATIONS.values()
        if res["user_id"] == user_id
    ]
    
    # Filtrar por status si se especifica
    if status:
        user_reservations = [r for r in user_reservations if r.get("status") == status]
    
    # Aplicar límite
    if limit:
        user_reservations = user_reservations[:limit]
    
    return user_reservations

@router.post("/reservations", response_model=ReservationResponse)
async def create_reservation(
    req: ReservationRequest,
    x_user_id: Optional[str] = Header(default=None, convert_underscores=False, alias="X-User-ID"),
):
    """Crea una reserva de créditos."""
    try:
        # Hook para testing de errores internos
        if hasattr(create_reservation, "_test_error"):
            error = getattr(create_reservation, "_test_error")
            if error:
                raise error
        
        user_id = int(x_user_id) if x_user_id else 1
        
        # Validaciones
        if req.credits <= 0:
            raise HTTPException(status_code=422, detail="credits must be positive")
        
        if not req.operation_code or req.operation_code.strip() == "":
            raise HTTPException(status_code=422, detail="operation_code is required")
        
        # Idempotencia
        if req.idempotency_key and req.idempotency_key in _RESERVATION_IDEM:
            return _RESERVATION_IDEM[req.idempotency_key]
        
        # Verificar balance
        wallet = _WALLETS.get(user_id)
        if not wallet:
            raise HTTPException(status_code=404, detail="Wallet not found")
        
        if wallet["balance_available"] < req.credits:
            raise HTTPException(status_code=400, detail="Insufficient balance available")
        
        # Crear reservación
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        
        reservation_id = len(_RESERVATIONS) + 1
        reservation = {
            "reservation_id": reservation_id,
            "user_id": user_id,
            "credits": req.credits,
            "status": "created",
            "created_at": now.isoformat(),
            "consumed_at": None,
            "released_at": None,
        }
        
        # Guardar
        _RESERVATIONS[reservation_id] = reservation
        if req.idempotency_key:
            _RESERVATION_IDEM[req.idempotency_key] = reservation
        
        # Actualizar wallet
        wallet["balance_available"] -= req.credits
        wallet["balance_reserved"] += req.credits
        
        return reservation
    except HTTPException:
        raise
    except Exception as exc:
        # Capturar errores internos y retornar 500
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {exc.__class__.__name__}"
        )

@router.get("/reservations/{reservation_id}")
async def get_reservation(
    reservation_id: int,
    x_user_id: Optional[str] = Header(default=None, convert_underscores=False, alias="X-User-ID"),
):
    """Consulta el estado de una reserva."""
    user_id = int(x_user_id) if x_user_id else 1
    
    # Buscar reservación
    reservation = _RESERVATIONS.get(reservation_id)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    
    if reservation["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    return reservation

class ReservationConsumeRequest(BaseModel):
    credits: int

@router.post("/reservations/{reservation_id}/consume")
async def consume_reservation(
    reservation_id: int,
    req: ReservationConsumeRequest,
    x_user_id: Optional[str] = Header(default=None, convert_underscores=False, alias="X-User-ID"),
):
    """Consume una reserva de créditos."""
    user_id = int(x_user_id) if x_user_id else 1
    
    # Buscar reservación
    reservation = _RESERVATIONS.get(reservation_id)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    
    if reservation["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if reservation["status"] == "consumed":
        raise HTTPException(status_code=400, detail="Reservation already consumed")
    
    if reservation["status"] == "released":
        raise HTTPException(status_code=400, detail="Reservation already released")
    
    if reservation["status"] == "expired":
        raise HTTPException(status_code=400, detail="Reservation expired")
    
    # Validar que no se consuman más créditos de los reservados
    if req.credits > reservation["credits"]:
        raise HTTPException(status_code=400, detail=f"Credits to consume ({req.credits}) exceed reserved amount ({reservation['credits']})")
    
    if req.credits <= 0:
        raise HTTPException(status_code=422, detail="credits must be positive")
    
    # Consumir
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    
    reservation["status"] = "consumed"
    reservation["consumed_at"] = now.isoformat()
    reservation["credits_consumed"] = req.credits
    
    # Actualizar wallet
    wallet = _WALLETS.get(user_id)
    if wallet:
        wallet["balance_reserved"] -= req.credits
        wallet["balance"] -= req.credits
    
    return reservation

@router.post("/reservations/{reservation_id}/release")
async def release_reservation(
    reservation_id: int,
    x_user_id: Optional[str] = Header(default=None, convert_underscores=False, alias="X-User-ID"),
):
    """Libera una reserva no utilizada."""
    user_id = int(x_user_id) if x_user_id else 1
    
    # Buscar reservación
    reservation = _RESERVATIONS.get(reservation_id)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    
    if reservation["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if reservation["status"] == "consumed":
        raise HTTPException(status_code=400, detail="Cannot release consumed reservation")
    
    if reservation["status"] == "released":
        raise HTTPException(status_code=400, detail="Reservation already released")
    
    if reservation["status"] == "expired":
        raise HTTPException(status_code=400, detail="Reservation expired")
    
    # Liberar
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    
    reservation["status"] = "released"
    reservation["released_at"] = now.isoformat()
    
    # Actualizar wallet
    wallet = _WALLETS.get(user_id)
    if wallet:
        wallet["balance_reserved"] -= reservation["credits"]
        wallet["balance_available"] += reservation["credits"]
    
    return reservation

# ============================================================
# FIN RESERVATIONS - AHORA WALLET ANTES DE RUTAS CON PARÁMETROS
# ============================================================

@router.get("/wallet")
async def get_wallet_balance(
    x_user_id: Optional[str] = Header(default=None, convert_underscores=False, alias="X-User-ID"),
):
    """Obtiene el balance del wallet del usuario."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user_id = int(x_user_id)
    
    # Intentar usar credit_service.get_wallet si está disponible (para permitir monkeypatching en tests)
    try:
        from app.modules.payments.services import credit_service
        if hasattr(credit_service, "get_wallet"):
            wallet = await credit_service.get_wallet(None, user_id)
            if wallet is None:
                raise HTTPException(status_code=404, detail="Wallet not found")
            return wallet
    except HTTPException:
        raise
    except Exception as e:
        # Error interno en la obtención del wallet
        raise HTTPException(
            status_code=500, 
            detail=f"Database failure: {str(e)}"
        )
    
    # Fallback al diccionario local si no hay credit_service
    wallet = _WALLETS.get(user_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    
    return {
        "user_id": wallet["user_id"],
        "balance": wallet["balance"],
        "balance_reserved": wallet["balance_reserved"],
        "balance_available": wallet["balance_available"],
        "currency": "usd"
    }

@router.get("/wallet/ledger")
async def get_wallet_ledger(
    x_user_id: Optional[str] = Header(default=None, convert_underscores=False, alias="X-User-ID"),
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    type: Optional[str] = None,
):
    """Obtiene el ledger (historial de transacciones) del wallet."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user_id = int(x_user_id)
    
    # Retornar lista vacía de transacciones (el test espera una lista directamente)
    transactions = []
    
    return transactions

@router.post("/wallet/recalculate")
async def recalculate_wallet(
    request: Request,
    x_user_id: Optional[str] = Header(default=None, convert_underscores=False, alias="X-User-ID"),
    user_id: Optional[int] = None,  # Query param
):
    """Recalcula el balance del wallet basándose en las transacciones."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    auth_user_id = int(x_user_id)
    
    # Si se especifica un user_id diferente al autenticado, rechazar
    if user_id is not None and user_id != auth_user_id:
        raise HTTPException(status_code=403, detail="Cannot recalculate wallet for another user")
    
    # Usar el user_id autenticado
    target_user_id = auth_user_id
    
    # Llamar al servicio real si estamos usando stubs
    from app.modules.payments.services import credit_service
    
    # En modo stub, simplemente retornar el wallet actual
    wallet = _WALLETS.get(target_user_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    
    # Si existe la función recalculate_wallet en el servicio, llamarla
    if hasattr(credit_service, "recalculate_wallet"):
        # Mock de db para el stub
        recalculated = await credit_service.recalculate_wallet(None, target_user_id)
        return recalculated
    
    return {
        "balance": wallet["balance"],
        "balance_available": wallet["balance_available"],
        "balance_reserved": wallet["balance_reserved"],
        "currency": "usd"
    }


# FIN WALLET - AHORA MÉTRICAS (antes de rutas con parámetros)
# ============================================================

# Importar routers de métricas para incluirlos ANTES de /{payment_id}
try:
    from app.modules.payments.metrics.routes import (
        router_prometheus,
        router_snapshot_memory,
        router_snapshot_db,
    )
    # Incluir métricas en el router principal para que se evalúen antes que /{payment_id}
    router.include_router(router_prometheus)
    router.include_router(router_snapshot_memory)
    router.include_router(router_snapshot_db)
except Exception as e:
    import logging
    logging.getLogger(__name__).warning(f"No se pudieron cargar routers de métricas en stubs: {e}")

# FIN MÉTRICAS - AHORA SIGUEN LAS RUTAS CON PARÁMETROS
# ============================================================

@router.get("/{payment_id}", response_model=IntentResponse)
async def get_payment_detail(
    payment_id: int,
    x_user_id: Optional[str] = Header(default=None, convert_underscores=False, alias="X-User-ID"),
):
    user_id = int(x_user_id) if x_user_id else 1
    payments = _PAYMENTS.get(user_id, [])
    
    for payment in payments:
        if payment["payment_id"] == payment_id:
            return payment
    
    raise HTTPException(status_code=404, detail="Payment not found")

@router.delete("/{payment_id}")
async def delete_payment(
    payment_id: int,
    x_user_id: Optional[str] = Header(default=None, convert_underscores=False, alias="X-User-ID"),
):
    user_id = int(x_user_id) if x_user_id else 1
    payments = _PAYMENTS.get(user_id, [])
    
    for i, payment in enumerate(payments):
        if payment["payment_id"] == payment_id:
            # No se puede cancelar un pago pagado
            if payment["status"] in ("paid", "succeeded", "completed"):
                raise HTTPException(status_code=403, detail="Cannot cancel paid payment")
            
            # Cancelar el pago (cambiar status o eliminarlo)
            payment["status"] = "cancelled"
            return JSONResponse({"message": "Payment cancelled"}, status_code=200)
    
    raise HTTPException(status_code=404, detail="Payment not found")

@router.post("/checkout/start", response_model=CheckoutResponse)
def checkout_start(
    req: CheckoutRequest,
):
    if not _validate_provider(req.provider):
        raise HTTPException(status_code=422, detail="provider inválido")
    if req.amount_cents <= 0 or req.credits_purchased <= 0:
        raise HTTPException(status_code=422, detail="monto/credits inválidos")
    if not _validate_currency(req.currency):
        raise HTTPException(status_code=422, detail="currency inválida")
    if not (_validate_url(req.success_url) and _validate_url(req.cancel_url)):
        raise HTTPException(status_code=422, detail="urls inválidas")

    # Usar client_nonce del payload
    client_nonce = req.client_nonce
    key = f"{req.provider.lower()}::{client_nonce or ''}::{req.amount_cents}::{req.currency.lower()}::{req.credits_purchased}"
    if client_nonce and key in _IDEM:
        return _IDEM[key]

    checkout_id = f"co_{client_nonce or 'no_nonce'}"
    provider_payment_id = f"prov_{req.provider.lower()}_{client_nonce or 'no_nonce'}"
    idempotency_key = f"idem_{client_nonce or 'no_nonce'}_{req.amount_cents}"
    
    resp = {
        "payment_id": hash(key) % 1000000,  # ID único basado en la clave
        "provider": req.provider.lower(),
        "provider_payment_id": provider_payment_id,
        "payment_url": f"https://example.local/checkout/{checkout_id}",
        "payment_status": "pending",
        "amount_cents": req.amount_cents,
        "currency": req.currency.lower(),
        "credits_purchased": req.credits_purchased,
        "idempotency_key": idempotency_key,
        "status": "pending",  # alias adicional
    }
    if client_nonce:
        _IDEM[key] = resp
    return resp

# Registrar también /checkout como alias de /checkout/start
router.add_api_route(
    "/checkout",
    checkout_start,
    methods=["POST"],
    response_model=CheckoutResponse,
    name="checkout_start_alias",
)

# ====== Webhooks: STRIPE ======
@router.post("/webhooks/stripe")
async def webhook_stripe(
    request: Request,
    body: Dict[str, Any] = Body(...),
    stripe_signature_uc: Optional[str] = Header(default=None, convert_underscores=False, alias="Stripe-Signature"),
    stripe_signature_lc: Optional[str] = Header(default=None, convert_underscores=False, alias="stripe-signature"),
):
    sig = (stripe_signature_uc or "") or (stripe_signature_lc or "")
    insecure = _allow_insecure()

    # Verificar si hay firma cuando no está en modo insecure
    if not insecure and not sig:
        raise HTTPException(status_code=401, detail="Falta encabezado de firma Stripe")

    # 422 si falta 'type'
    evt_type = body.get("type") if isinstance(body, dict) else None
    if not evt_type:
        raise HTTPException(
            status_code=422,
            detail="Webhook malformado: faltan event_type o provider_event_id",
        )

    # Verificar firma usando verify_stripe_webhook_signature (siempre que no sea insecure)
    if not insecure:
        from app.modules.payments.services.webhooks import signature_verification
        
        # Verificar firma - si retorna False, rechazar con 401
        # Para el stub, pasamos parámetros dummy ya que la función verificará basándose en el env
        is_valid = signature_verification.verify_stripe_webhook_signature(
            json.dumps(body).encode(), 
            sig, 
            "dummy_secret"
        )
        if not is_valid:
            raise HTTPException(status_code=401, detail="Invalid Stripe webhook signature")

    # Procesar evento usando manejadores de la fachada
    try:
        from app.modules.payments.facades.payments import webhook_handler

        # Preferir el manejador unificado v3 (usado en tests vía monkeypatch)
        if hasattr(webhook_handler, "handle_webhook"):
            result = await webhook_handler.handle_webhook(body)
            return JSONResponse(result, status_code=200)

        # Fallback legacy: handle_stripe_event si existiera
        if hasattr(webhook_handler, "handle_stripe_event"):
            result = await webhook_handler.handle_stripe_event(body)
            return JSONResponse(result, status_code=200)
    except Exception:
        pass

    # Clasificación por tipo (los tests miran 'called' y 'handled_event')
    base = {"result": {"provider": "stripe", "status": "received", "signature": sig or None}}
    success_types = {"payment_intent.succeeded", "charge.succeeded", "checkout.session.completed"}
    failed_types  = {"payment_intent.payment_failed", "charge.failed"}

    if evt_type in success_types:
        return JSONResponse({"status": "ok", "called": {"ok": evt_type}, **base}, status_code=200)

    if evt_type in failed_types:
        return JSONResponse({"status": "ok", "called": {"fail": evt_type}, **base}, status_code=200)

    # desconocidos → 'ignored' + handled_event
    return JSONResponse({"status": "ignored", "handled_event": evt_type, **base}, status_code=200)


# ====== Webhooks: PAYPAL ======
@router.post("/webhooks/paypal")
async def webhook_paypal(
    request: Request,
    body: Dict[str, Any] = Body(...),
    paypal_sig_lc: Optional[str] = Header(default=None, convert_underscores=False, alias="paypal-transmission-sig"),
    paypal_sig_uc: Optional[str] = Header(default=None, convert_underscores=False, alias="PAYPAL-TRANSMISSION-SIG"),
    paypal_tid_lc: Optional[str] = Header(default=None, convert_underscores=False, alias="paypal-transmission-id"),
    paypal_tid_uc: Optional[str] = Header(default=None, convert_underscores=False, alias="PAYPAL-TRANSMISSION-ID"),
    paypal_time_lc: Optional[str] = Header(default=None, convert_underscores=False, alias="paypal-transmission-time"),
    paypal_time_uc: Optional[str] = Header(default=None, convert_underscores=False, alias="PAYPAL-TRANSMISSION-TIME"),
):
    sig = (paypal_sig_lc or paypal_sig_uc)
    insecure = _allow_insecure()

    if not insecure and not sig:
        raise HTTPException(status_code=401, detail="Falta encabezado de firma PayPal")

    evt_type = body.get("event_type") if isinstance(body, dict) else None
    if evt_type is None:
        raise HTTPException(status_code=422, detail="Webhook malformado: faltan event_type o provider_event_id")

    # Verificar firma usando verify_paypal_webhook_signature (siempre que no sea insecure)
    if not insecure:
        from app.modules.payments.services.webhooks import signature_verification
        
        # Preparar headers para verificación
        headers = {
            "paypal-transmission-sig": sig,
            "paypal-transmission-id": (paypal_tid_lc or paypal_tid_uc),
            "paypal-transmission-time": (paypal_time_lc or paypal_time_uc),
        }
        
        # Verificar firma - si retorna False, rechazar con 401
        # Usar acceso por módulo para que sea parcheable en tests
        from app.modules.payments.facades.webhooks import verify as verify_mod
        is_valid = await verify_mod.verify_paypal_signature(body, headers)
        if not is_valid:
            raise HTTPException(status_code=401, detail="Invalid PayPal webhook signature")
    
    # Procesar evento usando handle_webhook
    try:
        from app.modules.payments.facades.payments import webhook_handler
        if hasattr(webhook_handler, "handle_webhook"):
            # Importar servicios necesarios
            from app.modules.payments.enums import PaymentProvider
            
            # Construir servicios básicos para el handler
            from app.modules.payments.repositories import (
                PaymentRepository,
                RefundRepository,
                PaymentEventRepository,
                WalletRepository,
                CreditTransactionRepository,
            )
            from app.modules.payments.services import (
                PaymentService,
                RefundService,
                PaymentEventService,
                WalletService,
                CreditService,
            )
            from sqlalchemy.ext.asyncio import AsyncSession
            from app.shared.database.database import get_async_session
            
            # Obtener sesión de BD
            # Para stubs, podemos usar None o una sesión mock simple
            db_session = None  # El handler real maneja la ausencia de sesión en tests
            
            payment_repo = PaymentRepository()
            refund_repo = RefundRepository()
            event_repo = PaymentEventRepository()
            wallet_repo = WalletRepository()
            credit_repo = CreditTransactionRepository()
            
            credit_service = CreditService(credit_repo)
            wallet_service = WalletService(wallet_repo=wallet_repo, credit_repo=credit_repo)
            payment_service = PaymentService(
                payment_repo=payment_repo,
                wallet_repo=wallet_repo,
                wallet_service=wallet_service,
                credit_service=credit_service,
            )
            refund_service = RefundService(
                refund_repo=refund_repo,
                payment_repo=payment_repo,
                credit_service=credit_service,
            )
            event_service = PaymentEventService(event_repo=event_repo)
            
            # Preparar raw_body y headers
            raw_body = json.dumps(body).encode("utf-8")
            headers_dict = {
                "paypal-transmission-sig": sig or "",
                "paypal-transmission-id": (paypal_tid_lc or paypal_tid_uc or ""),
                "paypal-transmission-time": (paypal_time_lc or paypal_time_uc or ""),
            }
            
            result = await webhook_handler.handle_webhook(
                session=db_session,
                provider=PaymentProvider.PAYPAL,
                raw_body=raw_body,
                headers=headers_dict,
                payment_service=payment_service,
                payment_repo=payment_repo,
                refund_service=refund_service,
                refund_repo=refund_repo,
                event_service=event_service,
            )
            return JSONResponse(result, status_code=200)
    except Exception:
        pass

    # OK en firma válida o modo inseguro; desconocidos también 200
    return JSONResponse(
        {
            "ok": True,
            "status": "received",
            "result": {"provider": "paypal", "status": "received", "signature": sig or "sig"},
        },
        status_code=200,
    )

# ===== RECIBOS =====
class ReceiptResponse(BaseModel):
    receipt_id: int
    receipt_url: str
    storage_path: str
    expires_at: str
    signed_at: Optional[str] = None

@router.post("/{payment_id}/receipts", response_model=ReceiptResponse)
async def generate_receipt(
    payment_id: int,
    x_user_id: Optional[str] = Header(default=None, convert_underscores=False, alias="X-User-ID"),
):
    """Genera recibo PDF para pagos elegibles (paid/refunded)."""
    user_id = int(x_user_id) if x_user_id else 1
    
    # Buscar el pago en los pagos almacenados
    payments = _PAYMENTS.get(user_id, [])
    payment = None
    for p in payments:
        if p["payment_id"] == payment_id:
            payment = p
            break
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    # Validar elegibilidad
    if payment["status"] not in ("paid", "refunded", "succeeded", "completed"):
        raise HTTPException(status_code=400, detail="Payment not eligible for receipt")
    
    # SIEMPRE llamar al generator (para monkeypatch en tests), pero preservar path existente
    from datetime import datetime, timezone, timedelta
    from app.modules.payments.facades.receipts import generator
    
    # Crear objeto Payment mock para pasar al generator
    class MockPayment:
        def __init__(self, data):
            self.id = data["payment_id"]
            self.amount_cents = data.get("amount_cents", 0)
            self.currency = type('obj', (object,), {'value': data.get("currency", "mxn")})()
            self.status = type('obj', (object,), {'value': data.get("status", "paid")})()
            self.credits_purchased = data.get("credits_purchased", 0)
            self.provider = type('obj', (object,), {'value': data.get("provider", "stripe")})()
            self.provider_payment_id = data.get("provider_payment_id")
            self.created_at = datetime.now(timezone.utc)
    
    mock_payment = MockPayment(payment)
    
    # Verificar si ya existe un recibo para preservar el path
    existing_receipt = _RECEIPTS.get(payment_id)
    
    try:
        # Llamar al generator (puede ser mockeado en tests)
        pdf_result = await generator.generate_receipt_pdf(mock_payment)
        
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=24)
        
        # Si existe un recibo previo, preservar el storage_path
        storage_path = existing_receipt["storage_path"] if existing_receipt else pdf_result.get("storage_path", f"receipts/receipt_{payment_id}.pdf")
        
        receipt = {
            "receipt_id": payment_id * 1000,
            "receipt_url": f"https://storage.doxai.test/receipts/{storage_path}?sig=fake_signature&exp={int(expires.timestamp())}",
            "storage_path": storage_path,
            "expires_at": expires.isoformat(),
            "signed_at": pdf_result.get("signed_at", now.isoformat()),
        }
    except RuntimeError as e:
        # Propagar errores de generación como 500
        raise HTTPException(status_code=500, detail=f"Error generating receipt: {str(e)}")
    except Exception as e:
        # Para otras excepciones inesperadas, también 500
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
    
    _RECEIPTS[payment_id] = receipt
    return ReceiptResponse(**receipt)

@router.get("/{payment_id}/receipt-url")
async def get_receipt_url(
    payment_id: int,
    x_user_id: Optional[str] = Header(default=None, convert_underscores=False, alias="X-User-ID"),
):
    """Obtiene URL firmada del recibo (regenera si expiró)."""
    user_id = int(x_user_id) if x_user_id else 1
    
    # Buscar el pago
    payments = _PAYMENTS.get(user_id, [])
    payment = None
    for p in payments:
        if p["payment_id"] == payment_id:
            payment = p
            break
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    # Verificar si existe recibo
    if payment_id not in _RECEIPTS:
        raise HTTPException(status_code=404, detail="Receipt not found. Generate receipt first.")
    
    # Regenerar URL firmada usando el módulo signer (para soportar monkeypatch en tests)
    from app.modules.payments.facades.receipts import signer
    
    receipt = _RECEIPTS[payment_id]
    storage_path = receipt['storage_path']
    
    # Usar la función sign_receipt_url del módulo signer (puede ser mockeada en tests)
    new_url = signer.sign_receipt_url(storage_path, expires_in=3600)
    
    # Actualizar en memoria
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=1)
    
    receipt["receipt_url"] = new_url
    receipt["expires_at"] = expires.isoformat()
    
    return new_url

# ===== RECONCILIACIÓN =====
class ReconciliationRequest(BaseModel):
    provider: str
    start_date: str
    end_date: str
    include_matched: Optional[bool] = False

class ReconciliationResponse(BaseModel):
    provider: str
    period: Dict[str, str]
    summary: Dict[str, Any]
    discrepancies: list

@router.post("/reconciliation/report", response_model=ReconciliationResponse)
async def generate_reconciliation_report(
    req: ReconciliationRequest,
    x_user_id: Optional[str] = Header(default=None, convert_underscores=False, alias="X-User-ID"),
):
    """Genera reporte de conciliación por proveedor y rango de fechas."""
    # Validar proveedor
    if not _validate_provider(req.provider):
        raise HTTPException(status_code=422, detail="provider inválido")
    
    # Validar fechas
    try:
        from datetime import datetime
        start_dt = datetime.fromisoformat(req.start_date.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(req.end_date.replace('Z', '+00:00'))
        
        if start_dt > end_dt:
            raise HTTPException(status_code=422, detail="start_date debe ser menor que end_date")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Formato de fecha inválido: {str(e)}")
    
    # Intentar usar el módulo de reconciliación (puede ser mockeado en tests)
    try:
        from app.modules.payments.facades.reconciliation import report
        
        # Intentar llamar con una función auxiliar que puede ser mockeada
        result = await report.generate_reconciliation_report(
            provider=req.provider,
            start_date=req.start_date,
            end_date=req.end_date,
            include_matched=req.include_matched,
        )
        
        return ReconciliationResponse(**result)
        
    except (RuntimeError, TypeError) as e:
        # Si falla (por mock o por falta de db), propagar como 500
        if isinstance(e, RuntimeError):
            raise HTTPException(status_code=500, detail=f"Reconciliation failure: {str(e)}")
        
        # Si es TypeError por falta de argumentos, generar reporte stub
        user_id = int(x_user_id) if x_user_id else 1
        payments = _PAYMENTS.get(user_id, [])
        
        # Filtrar pagos por proveedor
        filtered_payments = [p for p in payments if p.get("provider") == req.provider]
        
        # Generar discrepancias simuladas
        discrepancies = []
        for p in filtered_payments[:2]:  # Simulamos 2 discrepancias
            discrepancies.append({
                "payment_id": p["payment_id"],
                "provider_payment_id": p.get("provider_payment_id"),
                "status_db": p.get("status", "pending"),
                "status_provider": "completed",
                "amount_db": p.get("amount_cents", 0),
                "amount_provider": p.get("amount_cents", 0),
                "discrepancy_type": "status_mismatch",
            })
        
        # Si no se incluyen matched, solo retornar discrepancias
        if not req.include_matched:
            discrepancies = [d for d in discrepancies if d["discrepancy_type"] != "matched"]
        
        return ReconciliationResponse(
            provider=req.provider,
            period={
                "start_date": req.start_date,
                "end_date": req.end_date,
            },
            summary={
                "total_payments": len(filtered_payments),
                "matched": len(filtered_payments) - len(discrepancies),
                "discrepancies_count": len(discrepancies),
                "total_amount_cents": sum(p.get("amount_cents", 0) for p in filtered_payments),
            },
            discrepancies=discrepancies,
        )

@router.get("/reconciliation/summary")
async def get_reconciliation_summary(
    x_user_id: Optional[str] = Header(default=None, convert_underscores=False, alias="X-User-ID"),
):
    """Obtiene resumen global de reconciliación."""
    from datetime import datetime, timezone
    
    user_id = int(x_user_id) if x_user_id else 1
    payments = _PAYMENTS.get(user_id, [])
    
    total = len(payments)
    matched = len([p for p in payments if p.get("status") in ("paid", "succeeded", "completed")])
    unmatched = total - matched
    
    return {
        "provider": "aggregate",
        "total_payments": total,
        "matched": matched,
        "unmatched": unmatched,
        "last_run": datetime.now(timezone.utc).isoformat(),
    }

# ===== REFUNDS =====
class RefundRequest(BaseModel):
    amount_cents: Optional[int] = None  # None = refund total
    reason: Optional[str] = None
    idempotency_key: Optional[str] = None

class RefundResponse(BaseModel):
    refund_id: int
    payment_id: int
    amount_cents: int
    status: str
    reason: Optional[str] = None
    created_at: str

@router.post("/{payment_id}/refunds")
async def create_refund(
    payment_id: int,
    req: RefundRequest,
    x_user_id: Optional[str] = Header(default=None, convert_underscores=False, alias="X-User-ID"),
):
    """Crea un reembolso para un pago."""
    # Ya no necesitamos llamar a _seed_test_payments aquí porque el fixture autouse lo hace antes de cada test
    
    user_id = int(x_user_id) if x_user_id else 1
    
    # Idempotencia
    if req.idempotency_key and req.idempotency_key in _REFUND_IDEM:
        existing = _REFUND_IDEM[req.idempotency_key]
        return {
            "refund": existing,
            "payment": {"payment_id": payment_id, "status": "refunded"},
            "credit_reversal": {"type": "reversal", "amount_cents": existing["amount_cents"], "user_id": user_id}
        }
    
    # Buscar el pago
    payments = _PAYMENTS.get(user_id, [])
    payment = None
    for p in payments:
        if p["payment_id"] == payment_id:
            payment = p
            break
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    # Validar elegibilidad
    if payment["status"] not in ("paid", "succeeded", "completed", "partially_refunded"):
        raise HTTPException(status_code=400, detail="Payment not eligible for refund. Only paid payments can be refunded.")
    
    if payment["status"] == "refunded":
        raise HTTPException(status_code=400, detail="Payment already refunded")
    
    # Calcular total ya reembolsado
    existing_refunds = _REFUNDS.get(payment_id, [])
    total_refunded = sum(r["amount_cents"] for r in existing_refunds)
    
    # Validar amount
    payment_amount = payment.get("amount_cents", 0)
    remaining_amount = payment_amount - total_refunded
    refund_amount = req.amount_cents if req.amount_cents is not None else remaining_amount
    
    if refund_amount <= 0:
        raise HTTPException(status_code=422, detail="amount_cents must be positive")
    
    if refund_amount > remaining_amount:
        raise HTTPException(status_code=422, detail=f"amount_cents cannot exceed remaining amount ({remaining_amount} cents)")
    
    # Intentar usar el módulo de refunds (puede ser mockeado en tests)
    try:
        from app.modules.payments.facades.payments import refunds
        
        # Esta función puede lanzar RuntimeError si el provider falla
        await refunds.refund_via_provider(payment_id=payment_id, amount_cents=refund_amount)
        
    except RuntimeError as e:
        # Error del proveedor
        raise HTTPException(status_code=502, detail=f"Provider API failure: {str(e)}")
    except (ImportError, AttributeError, TypeError):
        # Módulo no existe o falla, continuar con stub
        pass
    
    # Crear refund
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    
    refund_id = payment_id * 1000 + len(_REFUNDS.get(payment_id, []))
    
    refund = {
        "refund_id": refund_id,
        "payment_id": payment_id,
        "amount_cents": refund_amount,
        "status": "succeeded" if refund_amount == payment_amount else "pending",
        "reason": req.reason,
        "created_at": now.isoformat(),
    }
    
    # Guardar refund
    if payment_id not in _REFUNDS:
        _REFUNDS[payment_id] = []
    _REFUNDS[payment_id].append(refund)
    
    if req.idempotency_key:
        _REFUND_IDEM[req.idempotency_key] = refund
    
    # Actualizar status del payment
    payment["status"] = "refunded" if refund_amount == payment_amount else "partially_refunded"
    
    return {
        "refund": refund,
        "payment": {"payment_id": payment_id, "status": payment["status"]},
        "credit_reversal": {
            "type": "reversal",
            "amount_cents": refund_amount,
            "user_id": user_id,
        }
    }

@router.get("/{payment_id}/refunds")
async def list_refunds(
    payment_id: int,
    x_user_id: Optional[str] = Header(default=None, convert_underscores=False, alias="X-User-ID"),
):
    """Lista todos los reembolsos de un pago."""
    user_id = int(x_user_id) if x_user_id else 1
    
    # Buscar el pago
    payments = _PAYMENTS.get(user_id, [])
    payment = None
    for p in payments:
        if p["payment_id"] == payment_id:
            payment = p
            break
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    return _REFUNDS.get(payment_id, [])

# ===== RESERVATIONS =====
_RESERVATIONS: dict[int, Dict[str, Any]] = {}  # reservation_id -> reservation data
_RESERVATION_IDEM: dict[str, Dict[str, Any]] = {}  # idempotency_key -> reservation
_WALLETS: dict[int, Dict[str, Any]] = {
    1: {"user_id": 1, "balance": 2000, "balance_available": 1800, "balance_reserved": 200},
    2: {"user_id": 2, "balance": 10, "balance_available": 10, "balance_reserved": 0},
}
# ============================================================
# WALLET
# ============================================================

# ... keep existing code (wallet section)

# Fin del archivo backend\app\modules\payments\routes\_stubs_tests_routes.py
