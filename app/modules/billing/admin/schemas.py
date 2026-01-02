# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/admin/schemas.py

Esquemas Pydantic para métricas financieras de Billing.
Define estructuras de salida limpias (sin PII) para
exponer snapshots de métricas al panel administrativo.

Autor: DoxAI
Fecha: 2026-01-01
"""
from typing import Optional
from pydantic import BaseModel, Field


class BillingFinanceSnapshot(BaseModel):
    """
    Snapshot de métricas financieras para Admin → Billing → Finanzas.
    
    Campos orientados a negocio, no a debugging:
    - revenue_*: métricas de ingresos
    - paying_users_*: usuarios con pagos
    - conversion_*: tasas de conversión
    """
    
    # ─────────────────────────────────────────────────────────────
    # Ingresos
    # ─────────────────────────────────────────────────────────────
    revenue_total_cents: int = Field(
        0,
        description="Ingresos totales históricos en centavos (checkouts completados)"
    )
    revenue_7d_cents: int = Field(
        0,
        description="Ingresos últimos 7 días en centavos"
    )
    revenue_30d_cents: int = Field(
        0,
        description="Ingresos últimos 30 días en centavos"
    )
    currency: str = Field(
        "MXN",
        description="Moneda principal (ISO 4217)"
    )
    
    # ─────────────────────────────────────────────────────────────
    # Checkouts y usuarios
    # ─────────────────────────────────────────────────────────────
    checkouts_completed_total: int = Field(
        0,
        description="Total de checkouts completados"
    )
    paying_users_total: int = Field(
        0,
        description="Usuarios únicos con ≥1 pago exitoso"
    )
    users_activated_total: int = Field(
        0,
        description="Usuarios vigentes activados (base para conversión)"
    )
    
    # ─────────────────────────────────────────────────────────────
    # Conversión y promedios
    # ─────────────────────────────────────────────────────────────
    conversion_activated_to_paid: float = Field(
        0.0,
        description="Tasa de conversión: paying_users / activated (0-1)"
    )
    avg_revenue_per_paying_user_cents: int = Field(
        0,
        description="Ingreso promedio por usuario que paga (centavos)"
    )
    
    # ─────────────────────────────────────────────────────────────
    # Meta
    # ─────────────────────────────────────────────────────────────
    generated_at: Optional[str] = Field(
        None,
        description="ISO timestamp de generación (DB)"
    )


# Fin del archivo backend/app/modules/billing/admin/schemas.py
