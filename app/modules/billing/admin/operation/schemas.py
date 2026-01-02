# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/admin/operation/schemas.py

Esquemas Pydantic para métricas operativas de Billing.
Define estructuras de salida limpias (sin PII) para
exponer snapshots de métricas al panel Admin → Billing → Operación.

Autor: DoxAI
Fecha: 2026-01-02
"""
from typing import Optional
from pydantic import BaseModel, Field


class BillingOperationSnapshot(BaseModel):
    """
    Snapshot de métricas operativas para Admin → Billing → Operación.
    
    Campos orientados a diagnóstico técnico, no a negocio:
    - public_access_*: accesos a recibos públicos
    - tokens_*: uso de tokens públicos
    - emails_*: métricas de envío de emails
    - *_errors_*: conteos de errores
    """
    
    # ─────────────────────────────────────────────────────────────
    # Recibos públicos
    # ─────────────────────────────────────────────────────────────
    public_pdf_access_total: int = Field(
        0,
        description="Total de PDFs públicos descargados exitosamente"
    )
    public_json_access_total: int = Field(
        0,
        description="Total de JSONs públicos consultados exitosamente"
    )
    public_access_total: int = Field(
        0,
        description="Total de accesos públicos (PDF + JSON)"
    )
    public_access_7d: int = Field(
        0,
        description="Accesos públicos últimos 7 días"
    )
    
    # ─────────────────────────────────────────────────────────────
    # Tokens
    # ─────────────────────────────────────────────────────────────
    tokens_valid_used_total: int = Field(
        0,
        description="Tokens válidos usados (accesos exitosos)"
    )
    tokens_expired_total: int = Field(
        0,
        description="Intentos con token expirado"
    )
    tokens_not_found_total: int = Field(
        0,
        description="Intentos con token inexistente"
    )
    tokens_expired_7d: int = Field(
        0,
        description="Tokens expirados usados últimos 7 días"
    )
    token_expiry_rate: float = Field(
        0.0,
        description="Ratio de tokens expirados / total de intentos (0-1)"
    )
    
    # ─────────────────────────────────────────────────────────────
    # Emails
    # ─────────────────────────────────────────────────────────────
    emails_sent_total: int = Field(
        0,
        description="Emails de compra enviados exitosamente"
    )
    emails_failed_total: int = Field(
        0,
        description="Emails de compra fallidos"
    )
    emails_failed_7d: int = Field(
        0,
        description="Emails fallidos últimos 7 días"
    )
    email_failure_rate: float = Field(
        0.0,
        description="Ratio de emails fallidos / total enviados (0-1)"
    )
    
    # ─────────────────────────────────────────────────────────────
    # Errores
    # ─────────────────────────────────────────────────────────────
    pdf_errors_total: int = Field(
        0,
        description="Errores de generación de PDF"
    )
    http_4xx_errors_total: int = Field(
        0,
        description="Errores HTTP 4xx (cliente, excluyendo auth)"
    )
    http_5xx_errors_total: int = Field(
        0,
        description="Errores HTTP 5xx (servidor)"
    )
    http_5xx_errors_7d: int = Field(
        0,
        description="Errores 5xx últimos 7 días"
    )
    
    # ─────────────────────────────────────────────────────────────
    # Meta
    # ─────────────────────────────────────────────────────────────
    generated_at: Optional[str] = Field(
        None,
        description="ISO timestamp de generación (DB)"
    )


# Fin del archivo
