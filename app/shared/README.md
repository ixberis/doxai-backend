# Backend Shared - DoxAI

Directorio de código compartido y reutilizable en toda la aplicación.

## Estructura

```
shared/
├── config/          # Configuración centralizada
│   ├── __init__.py
│   ├── settings.py  # Settings unificados (singleton)
│   └── constants.py # Constantes globales
│
├── database/        # Base de datos
│   ├── __init__.py
│   ├── database.py  # Engine, SessionLocal, get_db
│   └── base.py      # Base declarativa ORM
│
├── enums/           # Enums alineados a DB
│   ├── __init__.py  # Export centralizado + registry
│   ├── role_enum.py
│   ├── user_plan_enum.py
│   ├── activation_status_enum.py
│   ├── payment_provider_enum.py
│   ├── payment_status_enum.py
│   ├── currency_enum.py
│   ├── credit_tx_type_enum.py
│   ├── reservation_status_enum.py
│   ├── project_phase_enum.py
│   ├── email_status_enum.py
│   ├── email_type_enum.py
│   └── subscription_period_unit_enum.py
│
├── utils/           # Utilidades comunes
│   ├── __init__.py
│   ├── base_models.py       # UTF8SafeModel, EmailStr, Field
│   ├── http_exceptions.py   # Excepciones HTTP personalizadas
│   ├── security.py          # Hash passwords + JWT
│   └── validators.py        # Validadores comunes
│
└── templates/       # Templates renderizables
    ├── __init__.py
    └── emails/      # Templates de email HTML
        ├── activation.html
        ├── password_reset.html
        └── payment_receipt.html
```

## Uso

### Config
```python
from app.shared.config import settings

# Acceso directo
db_host = settings.db_host
jwt_secret = settings.jwt_secret

# Subsettings
azure_endpoint = settings.azure_di.endpoint
chunk_size = settings.chunking.max_tokens
```

### Enums
```python
from app.modules.auth.enums import UserRole, PaymentStatus, ProjectPhase

# Usar en código
if user.role == UserRole.ADMIN:
    ...

# Usar en modelos ORM
from app.modules.auth.enums import user_role_pg_enum

class User(Base):
    role = Column(user_role_pg_enum(), nullable=False)
```

### Database
```python
from app.shared.database import get_db, Base

# En routes
async def my_endpoint(db: AsyncSession = Depends(get_db)):
    ...

# En modelos
class MyModel(Base):
    __tablename__ = "my_table"
    ...
```

### Utils
```python
from app.shared.utils import (
    hash_password,
    create_access_token,
    validate_email,
    BadRequestException,
)

# Seguridad
hashed = hash_password("password123")
token = create_access_token({"sub": user_id})

# Validación
if not validate_email(email):
    raise BadRequestException("Email inválido")

# Excepciones
raise NotFoundException("Usuario no encontrado")
```

## Principios

1. **DRY (Don't Repeat Yourself)**: Todo código compartido debe estar aquí
2. **Single Source of Truth**: Una sola ubicación para configuración y definiciones
3. **Type Safety**: Usar enums y Pydantic para validación
4. **Consistencia**: Seguir convenciones de nombres y estructura

## Migración

Este directorio es parte de la migración modular. Código legacy en:
- `app/config/` → consolidado en `shared/config/settings.py`
- `app/enums/` → movido a `shared/enums/`
- `app/utils/` → consolidado en `shared/utils/`
- `app/db/` → movido a `shared/database/`

Código nuevo debe usar imports desde `app.shared.*`
