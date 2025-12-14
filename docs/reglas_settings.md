

# 🧩 Guía de desarrollo para archivos de configuración (`settings/config`)

## 📘 Propósito

Establecer las reglas para crear y mantener los archivos de configuración del sistema ubicados en  
`backend/app/shared/config`.

El objetivo es asegurar coherencia, seguridad y facilidad de despliegue en distintos entornos
(`development`, `test`, `production`), utilizando **Pydantic Settings v2** como base.

---

## 🏗️ Estructura recomendada del paquete

```

shared/config/
│
├── **init**.py                # Expone get_settings()
├── base_settings.py           # Configuración base (común a todos los entornos)
├── settings_dev.py            # Configuración específica para desarrollo
├── settings_test.py           # Configuración para testing
├── settings_prod.py           # Configuración de producción
├── config_loader.py           # Selección dinámica de clase según PYTHON_ENV
└── logging_config.py          # Configuración central de logging

````

---

## ⚙️ Uso de `pydantic-settings`

Usar siempre:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, HttpUrl, SecretStr, computed_field
from typing import Literal, Optional
````

### Ejemplo base

```python
class BaseAppSettings(BaseSettings):
    """Configuración base para todos los entornos."""

    python_env: Literal["development", "test", "production"] = Field(
        default="development",
        validation_alias="PYTHON_ENV"
    )

    app_name: str = Field(default="DoxAI")
    api_prefix: str = Field(default="/api")

    db_host: str = Field(default="localhost", validation_alias="DB_HOST")
    db_port: int = Field(default=5432, validation_alias="DB_PORT")
    db_user: str = Field(default="postgres", validation_alias="DB_USER")
    db_password: SecretStr = Field(default=SecretStr("postgres"), validation_alias="DB_PASSWORD")
    db_name: str = Field(default="postgres", validation_alias="DB_NAME")
    db_sslmode: str = Field(default="prefer", validation_alias="DB_SSLMODE")
    db_url: Optional[str] = Field(default=None, validation_alias="DB_URL")

    jwt_secret_key: SecretStr = Field(
        default=SecretStr("please-change-me"),
        validation_alias="JWT_SECRET_KEY"
    )
    jwt_algorithm: Literal["HS256", "RS256"] = Field(default="HS256")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @computed_field
    @property
    def database_url(self) -> str:
        """Genera la URL de conexión completa."""
        from urllib.parse import quote_plus

        if self.db_url:
            url = self.db_url
            return (
                url.replace("postgres://", "postgresql+asyncpg://")
                .replace("postgresql://", "postgresql+asyncpg://")
            )

        pw = quote_plus(self.db_password.get_secret_value())
        return (
            f"postgresql+asyncpg://{self.db_user}:{pw}@"
            f"{self.db_host}:{self.db_port}/{self.db_name}"
        )

    # ✅ Validaciones automáticas por entorno
    @classmethod
    def _check_prod_security(cls, values):
        env = values.get("python_env")
        if env == "production":
            jwt_key = values["jwt_secret_key"].get_secret_value()
            if len(jwt_key) < 32:
                raise ValueError("JWT_SECRET_KEY debe tener al menos 32 caracteres en producción")
            if values.get("db_sslmode") != "require":
                raise ValueError("DB_SSLMODE debe ser 'require' en producción")
        return values
```

---

## 🌱 Configuraciones por entorno

Cada entorno hereda de `BaseAppSettings` y redefine solo lo necesario.

### `settings_dev.py`

```python
from .base_settings import BaseAppSettings

class DevSettings(BaseAppSettings):
    """Configuración para entorno de desarrollo."""
    debug: bool = True
    db_host: str = "localhost"
    db_sslmode: str = "disable"
```

### `settings_test.py`

```python
from .base_settings import BaseAppSettings

class TestSettings(BaseAppSettings):
    """Configuración para entorno de pruebas."""
    debug: bool = True
    db_name: str = "test_db"
    db_sslmode: str = "disable"
```

### `settings_prod.py`

```python
from .base_settings import BaseAppSettings

class ProdSettings(BaseAppSettings):
    """Configuración para entorno de producción."""
    debug: bool = False

    model_config = {
        "env_file": None,  # No se carga archivo .env en producción
        "extra": "ignore",
    }
```

---

## 🧠 Loader por entorno

Archivo: `config_loader.py`

```python
from functools import lru_cache
import os
from .settings_dev import DevSettings
from .settings_test import TestSettings
from .settings_prod import ProdSettings
from .base_settings import BaseAppSettings

@lru_cache(maxsize=1)
def get_settings() -> BaseAppSettings:
    """Devuelve la configuración apropiada según PYTHON_ENV."""
    env = os.getenv("PYTHON_ENV", "development").lower()

    if env == "production":
        return ProdSettings()
    if env == "test":
        return TestSettings()
    return DevSettings()
```

Archivo `__init__.py`:

```python
from .config_loader import get_settings

__all__ = ["get_settings"]
```

---

## 🪵 Configuración de Logging

Archivo: `logging_config.py`

```python
import logging.config

def setup_logging(level="INFO", fmt="plain"):
    handlers = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if fmt == "json" else "default",
        }
    }

    formatters = {
        "default": {"format": "%(levelname)s [%(name)s]: %(message)s"},
        "json": {"()": "pythonjsonlogger.jsonlogger.JsonFormatter"},
    }

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": formatters,
        "handlers": handlers,
        "root": {"handlers": ["console"], "level": level},
    }

    logging.config.dictConfig(logging_config)
```

Campos sugeridos en `BaseAppSettings`:

```python
log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
    default="INFO", validation_alias="LOG_LEVEL"
)
log_format: Literal["plain", "json"] = Field(default="plain", validation_alias="LOG_FORMAT")
```

---

## 🌐 Configuración adicional (opcional)

### CORS

```python
cors_origins: list[str] | list[HttpUrl] = Field(default=["*"], validation_alias="CORS_ORIGINS")
```

### Sentry

```python
sentry_dsn: Optional[HttpUrl] = Field(default=None, validation_alias="SENTRY_DSN")
```

### Feature flags

```python
features_payments_enabled: bool = Field(default=True, validation_alias="FEATURES_PAYMENTS_ENABLED")
```

> ⚠️ No mezclar lógica de negocio dentro de los settings.
> Los flags deben usarse únicamente como toggles en el código de aplicación.

---

## 🔐 Buenas prácticas de seguridad

1. Usar `SecretStr` para contraseñas, claves API y JWT.
2. Evitar imprimir settings completos en logs.
3. Validar claves y modos SSL en producción (ver ejemplo de `_check_prod_security`).
4. Preferir `DB_URL` en CI/CD y despliegues productivos.
5. Nunca subir `.env` al repositorio.
6. Mantener `.env.example` con solo nombres de variables y ejemplos seguros.

---

## 🧩 Recomendaciones para `.env.example`

```bash
# === APP ===
PYTHON_ENV=development
APP_NAME=DoxAI
API_PREFIX=/api

# === DATABASE ===
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=postgres
DB_NAME=doxai
DB_SSLMODE=prefer
# DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/doxai

# === AUTH ===
JWT_SECRET_KEY=please-change-me
JWT_ALGORITHM=HS256

# === LOGGING ===
LOG_LEVEL=INFO
LOG_FORMAT=plain

# === CORS ===
CORS_ORIGINS=["http://localhost:3000"]

# === MONITOREO ===
SENTRY_DSN=

# === FEATURE FLAGS ===
FEATURES_PAYMENTS_ENABLED=true
```

---

## 🧾 Reglas de oro

1. **Solo variables necesarias.** Evitar redundancia.
2. **Nombres consistentes.** Siempre en mayúsculas con `_` y prefijos claros (`DB_`, `JWT_`, `LOG_`).
3. **Herencia mínima.** Subclases solo sobrescriben valores distintos.
4. **Seguridad antes que conveniencia.** Validar siempre en producción.
5. **No lógica.** Settings ≠ lógica de negocio.
6. **Logging homogéneo.** Centralizar formato y nivel.
7. **Carga única.** Usar `@lru_cache` en `get_settings()`.
8. **Compatibilidad con CI/CD.** Permitir override completo vía `DB_URL` o variables específicas.
9. **Evitar dependencias circulares.** Settings solo se importan, nunca importan módulos de negocio.
10. **Documentar cada variable** en `.env.example` y mantenerlo sincronizado con los campos del modelo.

---

✅ **Resultado esperado:**
Cada módulo del backend puede importar configuración así:

```python
from app.shared.config import get_settings
settings = get_settings()

print(settings.database_url)
print(settings.python_env)
```

Esto garantiza:

* Un único punto de configuración.
* Entornos seguros y coherentes.
* Carga rápida y validada por Pydantic.


```


