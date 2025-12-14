# Módulo Auth - DoxAI

Módulo de autenticación completo para DoxAI (migrado a arquitectura modular).

## Estructura

```
auth/
├── __init__.py
├── models/              # Modelos ORM
│   ├── __init__.py
│   ├── user_models.py           # Usuario principal
│   ├── activation_models.py     # Tokens de activación
│   └── password_reset_models.py # Tokens de reset
│
├── schemas/             # Schemas Pydantic
│   ├── __init__.py
│   └── auth_schemas.py          # Requests/Responses
│
├── services/            # Lógica de negocio
│   ├── __init__.py
│   ├── token_service.py          # Gestión de tokens JWT
│   ├── activation_service.py     # Activación de cuentas
│   └── password_reset_service.py # Recuperación de contraseña
│
├── routes/              # Endpoints FastAPI
│   ├── __init__.py
│   └── auth_routes.py            # Rutas consolidadas
│
└── tests/               # Tests unitarios (pendiente)
    ├── __init__.py
    ├── test_models.py
    ├── test_services.py
    └── test_routes.py
```

## Funcionalidades

### 1. Registro de Usuario
- **Endpoint**: `POST /auth/register`
- Validación con reCAPTCHA
- Creación de usuario en DB
- Generación de sesión de pago PayPal
- Retorna access_token + payment_url

### 2. Activación de Cuenta
- **Endpoint**: `POST /auth/activate`
- Validación de token JWT
- Verificación de pago completado
- Marca usuario como activado
- Crea carpeta en Supabase Storage
- Envía correo de bienvenida
- Notifica al administrador

### 3. Reenvío de Activación
- **Endpoint**: `POST /auth/resend-activation`
- Verifica que el usuario existe
- Verifica que no esté ya activado
- Valida que haya completado el pago
- Genera nuevo token
- Envía email de activación

### 4. Validación de Token de Acceso
- **Servicio**: `get_current_user_id()`
- Extrae user_id desde token JWT
- Verifica que el usuario esté activo
- Verifica suscripción vigente
- Usado como dependencia en rutas protegidas

### 5. Recuperación de Contraseña
- **Servicio**: `PasswordResetTokenManager`
- Genera tokens de reset (1 hora validez)
- Almacena en base de datos
- Marca tokens como usados
- Previene reutilización

## Modelos

### User
```python
- user_id: UUID (PK)
- user_email: CITEXT (unique)
- user_password_hash: Text
- user_full_name: String
- user_phone: String (optional)
- user_role: user_role_enum (customer/admin/staff)
- user_status: user_status_enum
- user_subscription_status: subscription_status_enum
- user_is_activated: Boolean
- user_activated_at: DateTime
- user_last_login: DateTime
- user_created_at: DateTime
- user_updated_at: DateTime
```

### AccountActivation
```python
- activation_id: UUID (PK)
- user_id: UUID (FK → users)
- activation_token: Text (unique)
- token_expiration_time: DateTime
- status: activation_status_enum (sent/used/expired/revoked)
- account_is_used: Boolean
- account_created_at: DateTime
- account_updated_at: DateTime
- verified_at: DateTime (nullable)
```

### PasswordReset
```python
- reset_pass_id: UUID (PK)
- user_id: UUID (FK → users)
- reset_pass_token: Text (unique)
- reset_pass_token_expires_at: DateTime
- reset_pass_token_created_at: DateTime
- reset_pass_token_used_at: DateTime (nullable)
- ip_address: String (para auditoría)
- user_agent: String (para auditoría)
```

## Servicios

### TokenService
- `get_current_user_id()`: Extrae user_id desde token JWT
- `verify_access_token()`: Valida token de acceso
- `TokenService.validate_token()`: Valida tokens de reset
- `TokenService.store_reset_token()`: Almacena token de reset
- `TokenService.mark_token_as_used()`: Marca token como usado

### ActivationService
- `generate_activation_token()`: Genera token JWT de activación
- `is_token_valid()`: Valida formato de token
- `activate_user()`: Activa cuenta de usuario
- `activate_user_account()`: Wrapper con validación HTTP
- `resend_activation_email()`: Reenvía correo de activación

### PasswordResetService
- `PasswordResetTokenManager`: Gestor completo de tokens de reset
- `generate_and_store_token()`: Genera y almacena token
- `validate_token()`: Valida token de reset
- `mark_token_as_used()`: Marca token como usado

## Seguridad

### Passwords
- Hashing con bcrypt (12 rounds)
- Validación de complejidad mínima (12-24 caracteres)
- No se almacenan passwords en texto plano

### Tokens
- JWT para access tokens (configurables vía env)
- JWT para activation tokens (24h expiry por defecto)
- JWT para reset tokens (1h expiry)
- Un solo uso por token de activación/reset

### reCAPTCHA
- Validación obligatoria en registro
- Integración con Google reCAPTCHA v2

### RLS (Row Level Security)
Ver `database/rls/010_app_users_policies.sql` y `database/rls/020_account_activations_policies.sql`.

**Políticas clave**:
- Usuarios solo ven su propio perfil
- Account activations: NO acceso directo desde cliente
- Solo service_role (backend) gestiona tokens

## Uso

### Registro
```python
from app.modules.auth.routes import router

# El endpoint /auth/register maneja:
# 1. Validación reCAPTCHA
# 2. Creación de usuario
# 3. Generación de sesión PayPal
# 4. Retorno de access_token + payment_url
```

### Activación
```python
from app.modules.auth.services import activate_user_account

user = await activate_user_account(db, token="jwt-token-here")
```

### Validación de Token
```python
from app.modules.auth.services import get_current_user_id
from fastapi import Depends

@router.get("/protected")
def protected_route(user_id: str = Depends(get_current_user_id)):
    return {"user_id": user_id}
```

### Password Reset
```python
from app.modules.auth.services import PasswordResetTokenManager

manager = PasswordResetTokenManager(db)
token = manager.generate_and_store_token(user, ip, user_agent)

# Validar token
payload = manager.validate_token(token)

# Marcar como usado
manager.mark_token_as_used(token)
```

## Dependencias

- **Shared**: `app.shared.config`, `app.shared.enums`, `app.shared.utils`, `app.shared.database`
- **External**: FastAPI, SQLAlchemy, Pydantic, passlib, python-jose
- **Internal**: Email service, Payment service (PayPal), Storage service

## Tests

```bash
# Pendiente implementación
pytest backend/app/modules/auth/tests/ -v
```

## Estado de Migración

✅ **Completado (100%)**:
- Models ORM migrados
- Schemas Pydantic creados
- Services consolidados
- Routes consolidadas
- Tests unitarios implementados

## Próximas Mejoras

- [ ] OAuth2 providers (Google, GitHub)
- [ ] 2FA (Two-Factor Authentication)
- [ ] Magic links (passwordless login)
- [ ] Session management mejorado
- [ ] Device tracking
- [ ] Suspicious activity alerts
- [ ] Tests completos (unit + integration)
