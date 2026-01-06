
# -*- coding: utf-8 -*-
"""
backend/app/shared/config/__init__.py

Punto único de acceso a la configuración:
    from app.shared.config import settings

Estrategia:
1) Si existe config_loader.load_settings() -> úsalo.
2) Si existe config_loader.get_settings()  -> úsalo (alias).
3) Si existen módulos de entorno -> intenta:
      - settings_testing:  Settings / TestingSettings / TestSettings
      - settings_development: Settings / DevSettings
      - settings_production:  Settings / ProdSettings
4) Fallback: Settings mínimos para poder importar en tests (SQLite memoria).

Además, envolvemos el objeto de settings real en un proxy que
devuelve valores por defecto para atributos ausentes (p. ej. jwt_*),
sin intentar mutar el modelo Pydantic subyacente.
"""

from __future__ import annotations
import os
from typing import Callable, Any, Mapping

_factory: Callable[[], object] | None = None

# 1) Intentar con config_loader.load_settings()
try:
    from .config_loader import load_settings as _load
    _factory = _load  # type: ignore[assignment]
except Exception:
    _factory = None

# 2) Intentar con config_loader.get_settings() si no hubo load_settings
if _factory is None:
    try:
        from .config_loader import get_settings as _get
        _factory = _get  # type: ignore[assignment]
    except Exception:
        _factory = None


def _try_import_candidates(mod_name: str, class_candidates: tuple[str, ...]):
    """Devuelve clase Settings si existe en el módulo dado, o None."""
    try:
        mod = __import__(f"{__name__}.{mod_name}", fromlist=["*"])
    except Exception:
        return None
    for cls_name in class_candidates:
        cls = getattr(mod, cls_name, None)
        if cls is not None:
            return cls
    return None


def _fallback_settings_factory():
    """
    Construye Settings según PYTHON_ENV si hay módulos de entorno;
    si no, devuelve un Settings mínimo para tests.
    """
    env = os.getenv("PYTHON_ENV", "").lower() or (
        "test" if os.getenv("PYTEST_CURRENT_TEST") else "dev"
    )

    # Probar módulos por entorno
    if env == "test":
        SettingsClass = _try_import_candidates(
            "settings_testing",
            ("Settings", "TestingSettings", "TestSettings"),
        )
        if SettingsClass:
            return SettingsClass()

    if env in {"dev", "development"}:
        SettingsClass = _try_import_candidates(
            "settings_development",
            ("Settings", "DevSettings"),
        )
        if SettingsClass:
            return SettingsClass()

    if env in {"prod", "production"}:
        SettingsClass = _try_import_candidates(
            "settings_production",
            ("Settings", "ProdSettings"),
        )
        if SettingsClass:
            return SettingsClass()

    # 4) Último recurso: Settings mínimos que permiten importar módulos en tests
    try:
        from pydantic import BaseSettings
    except Exception:  # pydantic no disponible (muy improbable)
        class BaseSettings:  # type: ignore
            pass

    class _MinimalTestSettings(BaseSettings):
        DATABASE_URL: str = "sqlite+aiosqlite:///:memory:"
        PAYMENTS_ALLOW_INSECURE_WEBHOOKS: bool = True
        APP_NAME: str = "DoxAI (tests)"
        PYTHON_ENV: str = "test"

    return _MinimalTestSettings()


# Seleccionar la fábrica
_factory = _factory or _fallback_settings_factory

# Lazy-load settings: no instanciar al importar (evita validaciones prematuras en tests)
_settings_base: object | None = None


def _get_settings_base() -> object:
    """Lazy-load settings instance (singleton)."""
    global _settings_base
    if _settings_base is None:
        _settings_base = _factory()
    return _settings_base


# Proxy que entrega defaults cuando el atributo no existe en _settings_base
class _SettingsProxy:
    __slots__ = ("_base_getter", "_defaults")

    def __init__(self, base_getter: Callable[[], object], defaults: Mapping[str, Any]) -> None:
        object.__setattr__(self, "_base_getter", base_getter)
        object.__setattr__(self, "_defaults", dict(defaults))

    def _get_base(self) -> object:
        return object.__getattribute__(self, "_base_getter")()

    def __getattr__(self, name: str) -> Any:
        base = self._get_base()
        if hasattr(base, name):
            return getattr(base, name)
        defaults = object.__getattribute__(self, "_defaults")
        if name in defaults:
            return defaults[name]
        # Mantener el mismo comportamiento de AttributeError
        raise AttributeError(f"{type(base).__name__!r} object has no attribute {name!r}")

    # Si alguno de tus módulos asigna atributos dinámicamente sobre `settings`,
    # permitimos set sólo si existe en el base; si no, se guarda en el proxy.
    def __setattr__(self, name: str, value: Any) -> None:
        base = self._get_base()
        if hasattr(base, name):
            setattr(base, name, value)  # respeta validaciones si el base lo permite
        else:
            # Guardar en defaults locales del proxy
            defaults = object.__getattribute__(self, "_defaults")
            defaults[name] = value

    # Exponer dict de defaults si alguien lo necesita (no obligatorio)
    def _get_defaults(self) -> Mapping[str, Any]:
        return dict(object.__getattribute__(self, "_defaults"))


# Defaults “amistosos para tests”
_DEFAULTS = {
    "jwt_secret": "test-secret",
    "jwt_algorithm": "HS256",
    "jwt_exp_minutes": 60,
    "PAYMENTS_ALLOW_INSECURE_WEBHOOKS": True,
}

# Singleton accesible como `settings` (lazy-load via getter)
settings = _SettingsProxy(_get_settings_base, _DEFAULTS)

__all__ = ["settings"]
# Fin del archivo