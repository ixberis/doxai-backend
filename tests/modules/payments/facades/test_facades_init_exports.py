"""
Test de estructura modular de facades v3.

En vez de validar una API global en facades/__init__, verifica que:
- Cada submódulo (checkout, payments, receipts, reconciliation, webhooks) es importable
- Los símbolos clave se pueden importar desde sus paquetes específicos
"""

def test_checkout_facade_structure():
    """Valida que el submódulo checkout está disponible y expone la API esperada."""
    from app.modules.payments.facades import checkout
    from app.modules.payments.facades.checkout import start_checkout, validators
    
    assert hasattr(checkout, "start_checkout")
    assert callable(start_checkout)


def test_payments_facade_structure():
    """Valida que el submódulo payments está disponible y expone intents, webhook_handler, refunds."""
    from app.modules.payments.facades import payments
    from app.modules.payments.facades.payments import intents, webhook_handler, refunds
    
    assert hasattr(intents, "get_payment_intent")
    assert hasattr(intents, "PaymentIntentNotFound")
    assert hasattr(webhook_handler, "handle_webhook")
    assert hasattr(webhook_handler, "WebhookSignatureError")
    assert hasattr(refunds, "process_manual_refund")


def test_receipts_facade_structure():
    """Valida que el submódulo receipts expone generator, signer, eligibility."""
    from app.modules.payments.facades import receipts
    from app.modules.payments.facades.receipts import generator, signer, eligibility
    
    assert hasattr(generator, "generate_receipt")
    assert hasattr(signer, "get_receipt_url")
    assert hasattr(eligibility, "regenerate_receipt")


def test_reconciliation_facade_structure():
    """Valida que el submódulo reconciliation expone core, report."""
    from app.modules.payments.facades import reconciliation
    from app.modules.payments.facades.reconciliation import core, report
    
    assert hasattr(core, "reconcile_provider_transactions")
    assert hasattr(core, "find_discrepancies")
    assert hasattr(core, "ReconciliationResult")
    assert hasattr(report, "generate_reconciliation_report")


def test_webhooks_facade_structure():
    """Valida que el submódulo webhooks expone handler, normalize, verify, success."""
    from app.modules.payments.facades import webhooks
    from app.modules.payments.facades.webhooks import handler, normalize, verify, success
    
    assert hasattr(handler, "verify_and_handle_webhook")
    assert hasattr(normalize, "normalize_webhook_payload")
    assert hasattr(verify, "verify_stripe_signature")
    assert hasattr(verify, "verify_paypal_signature")
    assert hasattr(success, "handle_payment_success")
# Fin del archivo