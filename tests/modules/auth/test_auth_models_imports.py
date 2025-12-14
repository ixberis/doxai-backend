
# tests/auth/test_auth_models_imports.py
import importlib

def test_models_package_exports_expected_symbols():
    pkg = importlib.import_module("app.modules.auth.models")
    # Ajusta los nombres a los que realmente exportas en models/__init__.py
    expected = [
        "User", "AppUser",
        "AccountActivation",
        "PasswordReset",
        "LoginAttempt",
        "UserSession",
    ]
    missing = [name for name in expected if not hasattr(pkg, name)]
    assert not missing, f"Faltan modelos exportados: {missing}"
# Fin del archivo tests/auth/test_auth_models_imports.py