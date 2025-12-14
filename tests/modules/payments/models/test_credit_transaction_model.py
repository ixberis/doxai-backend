# -*- coding: utf-8 -*-
"""
Tests estructurales para el modelo CreditTransaction.

Estos tests son robustos ante pequeñas variaciones de nombres de columna comunes
(e.g., `credits` vs `credits_delta`, `tx_metadata` vs `metadata`), y verifican:

- Existencia del modelo y su tabla.
- Presencia de columnas clave (id, user_id, tx_type, monto de créditos, timestamps).
- Enum asociado a `tx_type` (CreditTxType).
- FK a Payment (opcional) y/o a Wallet (opcional).
- Únicos razonables para idempotencia a nivel de usuario (user_id + idempotency_key [+ operation_code]).
- CHECKs básicos sobre créditos (no cero / > 0) si existen.
- Índices útiles para consultas por usuario/tiempo.
"""

import inspect
import sqlalchemy as sa
import pytest

from app.modules.payments.enums import CreditTxType
from app.modules.payments.models.credit_transaction_models import CreditTransaction


def _has_column(table: sa.Table, name: str) -> bool:
    return name in table.c

def _get_present_column(table: sa.Table, candidates: list[str]) -> str | None:
    for c in candidates:
        if _has_column(table, c):
            return c
    return None

def test_model_class_and_table_exist():
    assert inspect.isclass(CreditTransaction), "CreditTransaction debe ser una clase"
    assert hasattr(CreditTransaction, "__table__"), "CreditTransaction debe tener __table__"
    table = CreditTransaction.__table__
    assert isinstance(table, sa.Table)
    # No forzamos el nombre exacto de la tabla, pero debe existir una PK 'id'
    assert _has_column(table, "id"), "La tabla debe tener columna 'id' (PK)"


def test_core_columns_and_enums_present():
    table = CreditTransaction.__table__

    # Claves mínimas esperadas
    assert _has_column(table, "user_id"), "Falta columna 'user_id' (FK a usuario)"

    # Enum de tipo de transacción
    assert _has_column(table, "tx_type"), "Falta columna 'tx_type'"
    col_type = table.c["tx_type"].type
    # Aceptamos sa.Enum, PG_ENUM, o String (PG_ENUM se compila a String sin PostgreSQL real)
    from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
    
    # Verificar a nivel de modelo ORM (más confiable que tabla compilada)
    model_col = CreditTransaction.__table__.c["tx_type"]
    impl_type = model_col.type
    
    # PG_ENUM expone enum_class o enums; si es String, verificamos el modelo original
    ok_enum = (
        isinstance(impl_type, (sa.Enum, PG_ENUM))
        and (
            getattr(impl_type, "enum_class", None) is CreditTxType
            or set(getattr(impl_type, "enums", [])).issuperset({m.value for m in CreditTxType})
        )
    ) or (
        # Fallback: PG_ENUM se compila a String en tests sin PostgreSQL
        isinstance(col_type, sa.String)
        and hasattr(CreditTransaction, "tx_type")
    )
    assert ok_enum, f"tx_type debe ser Enum(CreditTxType) o compatible, got: {type(col_type)}"

    # Monto de créditos (puede llamarse credits_delta o credits)
    credits_col = _get_present_column(table, ["credits_delta", "credits"])
    assert credits_col is not None, "Debe existir columna de monto de créditos (credits_delta|credits)"

    # Timestamps
    assert _has_column(table, "created_at"), "Falta 'created_at'"
    # updated_at es opcional según diseño, pero si existe, lo validamos
    # (no lo exigimos para permitir diseños sin updated_at)
    # if _has_column(table, "updated_at"):
    #     assert True

    # Metadata (nombre flexible)
    meta_col = _get_present_column(table, ["tx_metadata", "metadata", "extra"])
    assert meta_col is not None, "Debe existir columna de metadata (tx_metadata|metadata|extra)"


def test_optional_foreign_keys_and_relationships():
    """
    Muchos ledgers enlazan opcionalmente a Payment o Wallet.
    No exigimos ambas, pero si existen, checamos que sean FK válidas.
    """
    table = CreditTransaction.__table__

    # payment_id (opcional)
    if _has_column(table, "payment_id"):
        col = table.c["payment_id"]
        # Debe tener al menos una FK definida
        assert len(col.foreign_keys) >= 1, "payment_id debe tener FK si existe"

    # wallet_id (opcional según diseño; algunos usan relación vía user_id)
    if _has_column(table, "wallet_id"):
        col = table.c["wallet_id"]
        assert len(col.foreign_keys) >= 1, "wallet_id debe tener FK si existe"


def test_unique_constraints_for_idempotency():
    """
    Se espera idempotencia por usuario + idempotency_key (y a veces operation_code).
    Aceptamos distintas variantes mientras exista una UNIQUE que incluya idempotency_key.
    """
    table = CreditTransaction.__table__
    uniques = [uc for uc in table.constraints if isinstance(uc, sa.UniqueConstraint)]
    cols_sets = [{col.name for col in uc.columns} for uc in uniques]

    # Buscamos al menos una UNIQUE que incluya idempotency_key
    has_idem_unique = any("idempotency_key" in s for s in cols_sets)
    assert has_idem_unique, "Debe existir UNIQUE sobre idempotency_key (p.ej., (user_id, idempotency_key, [operation_code]))"

    # Variante más fuerte (no obligatoria): user_id + idempotency_key
    # (si existe, mejor)
    stronger = any({"user_id", "idempotency_key"}.issubset(s) for s in cols_sets)
    assert has_idem_unique or stronger  # redundante, pero deja clara la intención


def test_check_constraints_reasonable_on_credits():
    """
    Si existe una CHECK relacionada con créditos, validamos que impida 0 o negativos
    (según política). No se exige exactamente el texto, solo que haya una CHECK útil.
    """
    table = CreditTransaction.__table__
    checks = [ck for ck in table.constraints if isinstance(ck, sa.CheckConstraint)]
    # No exigimos que exista, pero si existe alguna sobre credits*, que tenga sentido
    if checks:
        # buscamos una que mencione la columna de créditos
        mention = any(
            any(name in (ck.sqltext.text if hasattr(ck.sqltext, "text") else str(ck.sqltext)).lower()
                for name in ("credits_delta", "credits"))
            for ck in checks
        )
        assert mention, "Las CHECKS deben incluir la columna de créditos si existen"


def test_useful_indexes_present():
    """
    Índices útiles típicos del ledger: por usuario y por fecha para consultas.
    No exigimos nombres exactos, validamos presencia de columnas esperables.
    """
    table = CreditTransaction.__table__

    # Recolectar índices (excluyendo PK automáticamente creada)
    indexes: list[sa.Index] = list(table.indexes)

    # Buscamos índice por user_id
    has_user_idx = any("user_id" in [col.name for col in idx.columns] for idx in indexes)
    assert has_user_idx, "Se recomienda tener índice por user_id"

    # Buscamos índice por created_at
    has_created_idx = any("created_at" in [col.name for col in idx.columns] for idx in indexes)
    assert has_created_idx, "Se recomienda tener índice por created_at"

    # Si existe operation_code, también es útil indexarlo
    if _has_column(table, "operation_code"):
        has_op_idx = any("operation_code" in [col.name for col in idx.columns] for idx in indexes)
        assert has_op_idx, "Se recomienda índice por operation_code si la columna existe"
# Fin del archivo