
# tests/auth/test_auth_schemas.py
import inspect
from pydantic import BaseModel

import app.modules.auth.schemas as S


def _is_pydantic_model(obj) -> bool:
    return inspect.isclass(obj) and issubclass(obj, BaseModel)


def test_core_request_response_models_exist_and_are_pydantic():
    names = [
        # Core auth flows
        "RegisterRequest", "RegisterResponse",
        "LoginRequest", "LoginResponse",
        "ActivationRequest", "ResendActivationRequest",
        "PasswordResetRequest", "PasswordResetConfirmRequest",
        "RefreshRequest",
        "MessageResponse", "TokenResponse",
        # Users
        "UserOut",
        # Opcionales (si existen en tu paquete):
        "UserAdminView",
    ]
    for name in names:
        assert hasattr(S, name), f"Falta schema {name}"
        cls = getattr(S, name)
        assert _is_pydantic_model(cls), f"{name} no es Pydantic BaseModel"

def test_session_models_exist_if_exportados():
    # Estos pueden vivir en session_schemas y re-exportarse en __init__.py
    maybes = [
        "LoginAttemptOut", "SessionOut",
        "RevokeSessionResponse", "RevokeAllSessionsResponse",
    ]
    for name in maybes:
        if hasattr(S, name):
            assert _is_pydantic_model(getattr(S, name)), f"{name} debe ser BaseModel"
# Fin del archivo tests/auth/test_auth_schemas.py