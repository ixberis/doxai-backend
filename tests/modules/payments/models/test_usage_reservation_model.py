
# -*- coding: utf-8 -*-
"""
backend/tests/modules/payments/models/test_usage_reservation_model.py

Pruebas del modelo UsageReservation alineado con el esquema SQL real.
"""

from __future__ import annotations

from sqlalchemy import UniqueConstraint, Index, inspect

from app.modules.payments.models import UsageReservation


def test_tablename_and_columns():
    t = UsageReservation.__table__
    assert t.name == "usage_reservations"

    # Columnas esperadas según el SQL real
    expected_cols = {
        "id",
        "user_id",
        "credits_reserved",
        "credits_consumed",
        "job_id",
        "operation_code",
        "reservation_status",
        "idempotency_key",
        "reason",
        "reservation_expires_at",
        "consumed_at",
        "released_at",
        "expired_at",
        "created_at",
        "updated_at",
    }
    actual_cols = set(t.c.keys())
    for col in expected_cols:
        assert col in actual_cols, f"Missing column '{col}'. Found: {actual_cols}"


def test_constraints_and_indexes():
    t = UsageReservation.__table__

    # UniqueConstraint en (user_id, operation_code, job_id, idempotency_key)
    uq_sets = {
        tuple(sorted(col.name for col in c.columns))
        for c in t.constraints
        if isinstance(c, UniqueConstraint)
    }
    expected_uq = tuple(sorted(["user_id", "operation_code", "job_id", "idempotency_key"]))
    assert expected_uq in uq_sets, f"Missing unique constraint. Found: {uq_sets}"

    # Índice en (user_id, reservation_status)
    idx_cols = {
        tuple(sorted(col.name for col in i.columns))
        for i in t.indexes
        if isinstance(i, Index)
    }
    expected_idx = tuple(sorted(["user_id", "reservation_status"]))
    assert expected_idx in idx_cols, f"Missing index. Found: {idx_cols}"


def test_relationships_present():
    mapper = inspect(UsageReservation)
    rels = {r.key for r in mapper.relationships}

    # Relación con usuario
    assert "user" in rels, f"Missing relationship 'user'. Found: {rels}"


def test_compatibility_properties():
    """Verifica que las propiedades de compatibilidad existan."""
    # Solo verificamos que las propiedades estén definidas
    assert hasattr(UsageReservation, "status")
    assert hasattr(UsageReservation, "operation_id")
    assert hasattr(UsageReservation, "expires_at")


# Fin del archivo
