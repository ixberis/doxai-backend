# backend/tests/modules/payments/conftest.py
import types
import pytest
from app.main import app as fastapi_app

@pytest.fixture
def app():
    """Fixture que provee la instancia de la app FastAPI."""
    return fastapi_app

def _collect_candidates(module_attr_pairs):
    found = []
    for modpath, attr in module_attr_pairs:
        try:
            mod = __import__(modpath, fromlist=[attr])
            if hasattr(mod, attr):
                found.append(getattr(mod, attr))
        except Exception:
            pass
    return found

@pytest.fixture(autouse=True)
def override_injections(db):
    """
    Inyecta overrides de:
      - get_db
      - get_current_user
      - get_current_user_admin
    cubriendo las rutas de Payments sin importar de dónde hayan importado.
    """
    # 1) get_db
    get_db_candidates = _collect_candidates([
        ("app.shared.database.dependencies", "get_db"),
        ("app.shared.database.database", "get_db"),
        ("app.shared.database.session", "get_db"),
        ("app.shared.database.depends", "get_db"),
    ])

    async def _db_override():
        yield db

    for dep in get_db_candidates:
        fastapi_app.dependency_overrides[dep] = _db_override

    # 2) get_current_user
    user_candidates = _collect_candidates([
        ("app.modules.auth.dependencies", "get_current_user"),
        ("app.modules.auth.routes.dependencies", "get_current_user"),
        ("app.modules.auth.routes.security", "get_current_user"),
        ("app.shared.security.dependencies", "get_current_user"),
    ])

    class _TestUser:
        def __init__(self, user_id=1, email="test@dox.ai", is_admin=False):
            self.user_id = user_id
            self.email = email
            self.is_admin = is_admin

    async def _user_override():
        # Mínimo que consumen los routers: user_id / is_admin
        return _TestUser(user_id=1, email="test@dox.ai", is_admin=False)

    for dep in user_candidates:
        fastapi_app.dependency_overrides[dep] = _user_override

    # 3) get_current_user_admin
    admin_candidates = _collect_candidates([
        ("app.modules.auth.dependencies", "get_current_user_admin"),
        ("app.modules.auth.routes.dependencies", "get_current_user_admin"),
        ("app.modules.auth.routes.security", "get_current_user_admin"),
        ("app.shared.security.dependencies", "get_current_user_admin"),
    ])

    # IMPORTANTE: El fixture _override_current_user_dependency puede modificar este comportamiento
    # por lo que usamos una clase con estado mutable
    class _AdminState:
        def __init__(self):
            self.is_admin = True
            self.user_id = 1
    
    _admin_state = _AdminState()

    async def _admin_override():
        user = _TestUser(user_id=_admin_state.user_id, email="admin@dox.ai", is_admin=_admin_state.is_admin)
        if not user.is_admin:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
        return user

    for dep in admin_candidates:
        fastapi_app.dependency_overrides[dep] = _admin_override
    
    # Guardar referencia para que otros fixtures puedan modificarla
    fastapi_app._admin_state = _admin_state

    # 4) Cobertura adicional si algún router re-exportó dependencias locales
    # IMPORTANTE: Solo hacer esto si NO estamos usando stubs para evitar conflictos
    import os
    if os.getenv("USE_PAYMENT_STUBS", "").lower() != "true":
        try:
            from app.modules.payments import routes as _routes  # noqa
            for attr in dir(_routes):
                mod = getattr(_routes, attr)
                if isinstance(mod, types.ModuleType):
                    for name in ("get_db", "get_current_user", "get_current_user_admin"):
                        if hasattr(mod, name):
                            fastapi_app.dependency_overrides[getattr(mod, name)] = (
                                _db_override if name == "get_db"
                                else _admin_override if name.endswith("_admin")
                                else _user_override
                            )
        except Exception:
            pass

    yield

    # Limpieza
    for dep in list(fastapi_app.dependency_overrides.keys()):
        fastapi_app.dependency_overrides.pop(dep, None)


