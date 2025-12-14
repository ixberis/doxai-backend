# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/__init__.py

Módulo de pagos de DoxAI.

Este módulo gestiona:
- Registros de pagos (Stripe, PayPal)
- Saldos y transacciones de créditos
- Reservas y consumo de créditos
- Eventos de webhook de proveedores

Estructura:
- enums: Tipos de datos (PaymentProvider, PaymentStatus, Currency, etc.)
- models: Modelos ORM (Payment, CreditWallet, Refund, etc.)
- schemas: Validación y serialización Pydantic
- services: Lógica de negocio de bajo nivel
- facades: Funciones de alto nivel (API pública)

Autor: Ixchel Beristáin
Fecha: 26/10/2025


# ===== ENUMS =====
from .enums import (
    PaymentProvider,
    PaymentStatus,
    Currency,
    CreditTxType,
    ReservationStatus,
    UserPlan,
    PG_ENUM_REGISTRY,
    DEFAULT_SCHEMA,
)

# ===== MODELS (opcional, para uso interno) =====
from .models import (
    Payment,
    PaymentRecord,  # Alias legacy
    PaymentEvent,
    CreditWallet,
    CreditTransaction,
    UsageReservation,
    Refund,
)

# ===== SCHEMAS =====
from .schemas import (
    # Common
    PageMeta,
    # Checkout
    CheckoutStartRequest,
    CheckoutStartResponse,
    # Payments
    CreatePaymentRequest,
    ProcessPaymentRequest,
    PaymentOut,
    PaymentResponse,
    PaymentListResponse,
    PaymentRecordOut,  # Legacy
    PaymentRecordResponse,  # Legacy
    PaymentRecordListResponse,  # Legacy
    # Refunds
    RefundCreateRequest,
    RefundOut,
    RefundResponse,
    RefundListResponse,
    # Wallet
    WalletOut,
    WalletResponse,
    WalletUpdateRequest,
    # Ledger
    CreditTransactionOut,
    CreditTransactionListResponse,
    CreditTransactionCreateRequest,
    # Reservations
    ReservationCreateRequest,
    ReservationUpdateRequest,
    ReservationOut,
    ReservationResponse,
    ReservationListResponse,
    ReservationQuery,
    # Payment Events
    PaymentEventCreate,
    PaymentEventUpdate,
    PaymentEventOut,
    PaymentEventListResponse,
    PaymentEventQuery,
    # Webhooks
    WebhookIncomingRequest,
    WebhookProcessingResponse,
)

# ===== SERVICES (opcional, para uso interno) =====
from .services import (
    PaymentService,
    CreditService,
    PaymentEventService,
    RefundService,
)

# ===== FACADES (API pública de alto nivel) =====
from .facades import (
    # Checkout
    start_checkout,
    # Payments
    get_payment_intent,
    PaymentIntentNotFound,
    handle_webhook,
    WebhookSignatureError,
    process_manual_refund,
    refund,
    # Webhooks
    verify_and_handle_webhook,
    # Reconciliation
    reconcile_provider_transactions,
    find_discrepancies,
    generate_reconciliation_report,
    ReconciliationResult,
    # Receipts
    generate_receipt,
    get_receipt_url,
    regenerate_receipt,
)


__all__ = [
    # ===== ENUMS (tipos de datos) =====
    "PaymentProvider",
    "PaymentStatus",
    "Currency",
    "CreditTxType",
    "ReservationStatus",
    "UserPlan",
    "PG_ENUM_REGISTRY",
    "DEFAULT_SCHEMA",
    
    # ===== MODELS (ORM) =====
    "Payment",
    "PaymentRecord",
    "PaymentEvent",
    "CreditWallet",
    "CreditTransaction",
    "UsageReservation",
    "Refund",
    
    # ===== SCHEMAS (Pydantic) =====
    # Common
    "PageMeta",
    # Checkout
    "CheckoutStartRequest",
    "CheckoutStartResponse",
    # Payments
    "CreatePaymentRequest",
    "ProcessPaymentRequest",
    "PaymentOut",
    "PaymentResponse",
    "PaymentListResponse",
    "PaymentRecordOut",
    "PaymentRecordResponse",
    "PaymentRecordListResponse",
    # Refunds
    "RefundCreateRequest",
    "RefundOut",
    "RefundResponse",
    "RefundListResponse",
    # Wallet
    "WalletOut",
    "WalletResponse",
    "WalletUpdateRequest",
    # Ledger
    "CreditTransactionOut",
    "CreditTransactionListResponse",
    "CreditTransactionCreateRequest",
    # Reservations
    "ReservationCreateRequest",
    "ReservationUpdateRequest",
    "ReservationOut",
    "ReservationResponse",
    "ReservationListResponse",
    "ReservationQuery",
    # Payment Events
    "PaymentEventCreate",
    "PaymentEventUpdate",
    "PaymentEventOut",
    "PaymentEventListResponse",
    "PaymentEventQuery",
    # Webhooks
    "WebhookIncomingRequest",
    "WebhookProcessingResponse",
    
    # ===== SERVICES (lógica de negocio) =====
    "PaymentService",
    "CreditService",
    "PaymentEventService",
    "RefundService",
    
    # ===== FACADES (API pública) =====
    # Checkout
    "start_checkout",
    # Payments
    "get_payment_intent",
    "PaymentIntentNotFound",
    "handle_webhook",
    "WebhookSignatureError",
    "process_manual_refund",
    "refund",
    # Webhooks
    "verify_and_handle_webhook",
    # Reconciliation
    "reconcile_provider_transactions",
    "find_discrepancies",
    "generate_reconciliation_report",
    "ReconciliationResult",
    # Receipts
    "generate_receipt",
    "get_receipt_url",
    "regenerate_receipt",
]
# Fin del archivo
"""
__all__ = []