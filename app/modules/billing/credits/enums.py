# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/credits/enums.py

Enums para el sistema de créditos.

Sincronizados con: database/payments/01_types/01_enums_payments.sql

Autor: DoxAI
Fecha: 2025-12-30
"""

from enum import Enum


class CreditTxType(str, Enum):
    """
    Tipo de transacción en el ledger de créditos.
    
    Sincronizado con: credit_tx_type_enum en PostgreSQL
    """
    CREDIT = "credit"  # Abono (+credits)
    DEBIT = "debit"    # Cargo (-credits)


class ReservationStatus(str, Enum):
    """
    Estado de una reservación de créditos.
    
    Sincronizado con: reservation_status_enum en PostgreSQL
    """
    PENDING = "pending"      # Creada pero no confirmada
    ACTIVE = "active"        # Créditos apartados, en uso
    EXPIRED = "expired"      # TTL expirado sin consumir
    CONSUMED = "consumed"    # Consumida completamente
    CANCELLED = "cancelled"  # Cancelada manualmente


__all__ = [
    "CreditTxType",
    "ReservationStatus",
]
