# Tests — Payments

Batería de pruebas del módulo **payments**: `enums`, `models`, `facades`, `schemas`.

## Estructura

tests/
└─ modules/
└─ payments/
├─ enums/
├─ facades/
├─ models/
└─ schemas/


## Requisitos

- Virtualenv activado (ej.: `doxai-reloaded-env`)
- Variables de entorno para pruebas (si aplica):
  - `PYTHON_ENV=test`
  - `PAYMENTS_ALLOW_HTTP_LOCAL=true` (si tus validadores lo usan)
  - `PAYMENTS_ALLOW_INSECURE_WEBHOOKS=true` (si tus tests de webhooks lo necesitan)

> Nota: el `conftest.py` de facades ya setea parte del entorno durante los tests.

## Comandos (PowerShell / Bash)

### Ejecutar **todos** los tests de payments
```bash
pytest -q tests/modules/payments
