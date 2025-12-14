
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/__init__.py

Punto de entrada del paquete de fachadas del módulo Payments (v3).

Diseño:
- Para evitar errores de importación y dependencias circulares,
  este __init__ NO realiza imports automáticos de submódulos.
- En su lugar, cada facade se importa explícitamente desde su paquete:

  Ejemplos de uso:

      from app.modules.payments.facades.checkout import validators
      from app.modules.payments.facades.checkout.start_checkout import start_checkout

      from app.modules.payments.facades.payments import intents, webhook_handler
      from app.modules.payments.facades.payments.refunds import (
          refund_via_provider,
          process_manual_refund,
      )

      from app.modules.payments.facades.receipts import generator, eligibility
      from app.modules.payments.facades.reconciliation import core, report
      from app.modules.payments.facades.webhooks import handler, normalize, success

Autor: Ixchel Beristain
Fecha: 2025-11-21
"""

__all__: list[str] = []

# Fin del archivo backend/app/modules/payments/facades/__init__.py
