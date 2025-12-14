# -*- coding: utf-8 -*-
"""
Tests para backend.app.shared.enums

Cubre:
- Miembros/valores de EmailStatus y EmailType (StrEnum)
- str(member) y .value
- Fábricas email_status_pg_enum() y email_type_pg_enum() (name, create_type, enum_class, enums)
- PG_ENUM_REGISTRY (claves y que las fábricas funcionan)
- __all__ esperado + presencia condicional de ProjectState/ProjectPhase
"""

import importlib
import enum
import pytest

# Import del paquete compartido (maneja internamente la import condicional de ProjectState)
import app.shared.enums as shared_enums


# --------------------------------------------------------------------
# Especificaciones esperadas (según definición de los archivos fuente)
# --------------------------------------------------------------------
EMAIL_STATUS_VALUES = [
    # operativos
    "sent", "failed", "queued", "skipped",
    # entregabilidad/engagement
    "delivered", "opened", "bounced", "complained", "suppressed", "unsubscribed",
]
EMAIL_TYPE_VALUES = [
    # cuenta & auth
    "account_activation", "account_verified", "welcome",
    "login_success", "login_failure", "login_challenge_required",
    "account_locked", "account_deleted",
    # reset password
    "reset_password", "reset_password_request", "reset_password_success", "reset_password_failure",
    # perfil
    "profile_updated",
    # pagos (top-ups)
    "payment_succeeded", "payment_failed",
    # créditos
    "credits_added", "credits_low_balance", "credits_depleted", "credits_grant", "credits_adjusted",
    # alertas admin
    "admin_user_activated_alert", "admin_payment_alert",
]


# -----------------------------
# Miembros / valores / __str__
# -----------------------------
def test_email_status_members_and_str():
    cls = shared_enums.EmailStatus
    assert sorted([m.value for m in cls]) == sorted(EMAIL_STATUS_VALUES)
    for v in EMAIL_STATUS_VALUES:
        m = cls(v)
        # StrEnum → str(member) == value
        assert isinstance(m, enum.StrEnum)
        assert str(m) == v
        assert m.value == v


def test_email_type_members_and_str():
    cls = shared_enums.EmailType
    assert sorted([m.value for m in cls]) == sorted(EMAIL_TYPE_VALUES)
    for v in EMAIL_TYPE_VALUES:
        m = cls(v)
        assert isinstance(m, enum.StrEnum)
        assert str(m) == v
        assert m.value == v


# -----------------------------
# Fábricas PG_ENUM (SQLAlchemy)
# -----------------------------
@pytest.mark.parametrize(
    "name, factory, enum_cls, expected_values, expected_pg_name",
    [
        ("EmailStatus", shared_enums.email_status_pg_enum, shared_enums.EmailStatus, EMAIL_STATUS_VALUES, "email_status_enum"),
        ("EmailType",   shared_enums.email_type_pg_enum,   shared_enums.EmailType,   EMAIL_TYPE_VALUES,   "email_type_enum"),
    ],
)
def test_pg_enum_factories(name, factory, enum_cls, expected_values, expected_pg_name):
    pg_enum = factory()
    # Atributos típicos del ENUM del dialecto PG
    assert getattr(pg_enum, "name", None) == expected_pg_name
    # En shared: create_type=False por diseño
    assert getattr(pg_enum, "create_type", None) is False
    # Clase Enum asociada y valores que publicará
    assert getattr(pg_enum, "enum_class", None) is enum_cls
    enums = list(getattr(pg_enum, "enums", []))
    assert sorted(enums) == sorted(expected_values)


# -----------------------------
# Registry central
# -----------------------------
def test_registry_keys_and_factory_equivalence():
    reg = shared_enums.PG_ENUM_REGISTRY
    # claves mínimas siempre presentes
    expected = {"email_status_enum", "email_type_enum"}
    # si ProjectState se importó con éxito, el __init__ agrega project_state_enum
    if getattr(shared_enums, "project_state_pg_enum", None) is not None:
        expected |= {"project_state_enum"}

    assert set(reg.keys()) == expected

    # Consistencia: lo que hay en el registry produce el mismo ENUM que la fábrica directa
    key_to_pair = {
        "email_status_enum": (shared_enums.email_status_pg_enum, shared_enums.EmailStatus, EMAIL_STATUS_VALUES),
        "email_type_enum":   (shared_enums.email_type_pg_enum,   shared_enums.EmailType,   EMAIL_TYPE_VALUES),
    }
    # Condicionalmente, si existe
    if "project_state_enum" in reg:
        # No afirmamos valores de ProjectState aquí (viene de otro módulo);
        # sólo verificamos nombre/enum_class coherente si está presente.
        reg_factory = reg["project_state_enum"]
        obj = reg_factory()
        assert getattr(obj, "name", None) == "project_state_enum"

    for key, (direct_factory, enum_cls, values) in key_to_pair.items():
        obj_reg = reg[key]()
        obj_dir = direct_factory()
        assert getattr(obj_reg, "name", None) == getattr(obj_dir, "name", None)
        assert getattr(obj_reg, "enum_class", None) is enum_cls
        assert getattr(obj_dir, "enum_class", None) is enum_cls
        assert sorted(getattr(obj_reg, "enums", [])) == sorted(values)
        assert sorted(getattr(obj_dir, "enums", [])) == sorted(values)


# -----------------------------
# __all__ del paquete shared
# -----------------------------
def test_dunder_all_exports():
    pkg = importlib.import_module("app.shared.enums")
    assert isinstance(getattr(pkg, "__all__", None), list)
    exported = set(pkg.__all__)

    must_have = {
        "EmailStatus",
        "EmailType",
        "email_status_pg_enum",
        "email_type_pg_enum",
        "PG_ENUM_REGISTRY",
    }
    assert must_have.issubset(exported)

    # Si ProjectState se cargó, también debe estar exportado
    if getattr(pkg, "ProjectState", None) is not None:
        assert "ProjectState" in exported


# -----------------------------
# Alias condicional ProjectState
# -----------------------------
def test_project_state_conditional():
    # El paquete garantiza que, si falla la import de ProjectState, no rompe.
    ps = getattr(shared_enums, "ProjectState", None)
    # Si existe, debe ser un enum válido
    if ps is not None:
        assert hasattr(ps, "__members__")
