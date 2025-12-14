
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/services/webhooks/__init__.py

Servicios relacionados con webhooks de pagos.

Autor: Ixchel Beristain
Fecha: 2025-12-13
"""

from .signature_verification import (
    verify_stripe_signature,
    verify_paypal_signature_via_api,
)
from .payload_sanitizer import (
    sanitize_webhook_payload,
    extract_audit_fields,
    compute_payload_hash,
    PII_FIELDS,
    ALLOWED_FIELDS,
)

__all__ = [
    # Verificación de firmas
    "verify_stripe_signature",
    "verify_paypal_signature_via_api",
    
    # Sanitización
    "sanitize_webhook_payload",
    "extract_audit_fields",
    "compute_payload_hash",
    "PII_FIELDS",
    "ALLOWED_FIELDS",
]

# Fin del archivo backend/app/modules/payments/services/webhooks/__init__.py

