# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/admin/__init__.py

Punto de entrada del sub-módulo Admin de Billing.
Expone rutas de métricas financieras y operativas para el panel de administración.

Autor: DoxAI
Fecha: 2026-01-01
Actualizado: 2026-01-02 - Añadido operation router
"""

from .routes import router as billing_admin_router
from .operation import router as billing_operation_router

__all__ = ["billing_admin_router", "billing_operation_router"]
