
# -*- coding: utf-8 -*-
"""
backend/tests/modules/payments/models/test_payment_model.py

Pruebas del modelo Payment (versión v3, créditos prepagados).

Valida:
- Nombre de tabla y columnas
- Constraints e índices clave
- Relaciones ORM básicas
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import inspect, UniqueConstraint, Index

from app.modules.payments.models import Payment
from app.modules.payments.enums import PaymentProvider, PaymentStatus, Currency


def test_tablename_and_columns():
    t = Payment.__table__
    # Nombre de tabla
    assert t.name == "payments"
    # Columnas esperadas en el modelo v3
    cols = set(t.c.keys())
    expected = {
        "id",
        "user_id",
        "provider",
        "status",
        "currency",
        "amount",
        "credits_ruled",
        "credits_awarded",  # campo de créditos asignados
        "payment_id",       # alias lógico para compatibilidad (si aplica)
        "payment_intent_id",
        "idempotency_key",
        "metadata_json",
        "created_at",
        "updated_at",
    }
    # Sólo comprobamos que las claves críticas estén presentes (v3 usa amount_cents, credits_purchased)
    for name in ["id", "user_id", "provider", "status", "currency", "amount_cents", "credits_purchased",
                 "provider_payment_id", "idempotency_key", "payment_metadata", "created_at"]:
        assert name in cols, f"Missing column {name} in Payment table"


def test_constraints_and_indexes():
    t = Payment.__table__
    # v3 constraints: (provider, provider_payment_id) y (user_id, idempotency_key)
    unique_sets = {tuple(sorted(c.columns.keys())) for c in t.constraints if isinstance(c, UniqueConstraint)}
    assert ("provider", "provider_payment_id") in unique_sets, "Missing unique constraint on (provider, provider_payment_id)"
    assert ("idempotency_key", "user_id") in unique_sets, "Missing unique constraint on (user_id, idempotency_key)"

    # Índice en (user_id, status)
    idx_map = {tuple(sorted(ix.columns.keys())): ix.name for ix in t.indexes if isinstance(ix, Index)}
    assert ("status", "user_id") in idx_map, "Missing index on (user_id, status)"
    assert idx_map[("status", "user_id")] == "ix_payments_user_status"


def test_relationships_present():
    mapper = inspect(Payment)
    rel_names = {rel.key for rel in mapper.relationships}
    # Relaciones que deben existir en v3
    for expected in {"events", "refunds"}:
        assert expected in rel_names, f"Missing relationship: {expected}"
    # La relación 'user' es opcional (depende de si AppUser está registrado en la metadata),
    # por lo que no la forzamos aquí.
# Fin del archivo backend\tests\modules\payments\models\test_payment_model.py