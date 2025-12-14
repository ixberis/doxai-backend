
# tests/auth/test_auth_enums.py
import inspect
import enum

import app.modules.auth.enums as auth_enums


def _is_enum(cls) -> bool:
    return inspect.isclass(cls) and issubclass(cls, enum.Enum)


def test_enums_exist_and_are_enum():
    required = [
        "UserRole",
        "UserStatus",
        "ActivationStatus",
        "LoginFailureReason",
        "TokenType",
    ]
    for name in required:
        assert hasattr(auth_enums, name), f"Falta enum {name}"
        enum_cls = getattr(auth_enums, name)
        assert _is_enum(enum_cls), f"{name} no es un Enum"

def test_token_type_has_common_members():
    # Flexible: solo validamos que hay al menos 'bearer' o 'Bearer' (según tu implementación)
    TokenType = auth_enums.TokenType
    members = {m.name.lower(): m for m in TokenType}
    assert "bearer" in members or "jwt" in members, "TokenType debería incluir bearer/jwt"

def test_user_role_has_at_least_user_or_admin():
    UserRole = auth_enums.UserRole
    names = {m.name.lower() for m in UserRole}
    assert any(n in names for n in ["user", "admin"]), "UserRole debería incluir user/admin"
# Fin del archivo tests/auth/test_auth_enums.py