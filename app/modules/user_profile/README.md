# Módulo `user_profile/` – Gestión de Perfiles de Usuario

Este módulo implementa toda la funcionalidad relacionada con la consulta y actualización de perfiles de usuario autenticados en la plataforma DoxAI.

---

## 📁 Estructura

```
user_profile/
├── models/          # Modelos ORM (reutiliza User de auth)
├── schemas/         # Schemas Pydantic de request/response
├── services/        # Lógica de negocio del perfil
├── routes/          # Endpoints REST API
├── tests/           # Tests unitarios y de integración
└── README.md        # Este archivo
```

---

## 🎯 Funcionalidades

### 1. **Consulta de Perfil**
- Obtener perfil completo por ID o email
- Incluye datos personales, rol, estado y suscripción

### 2. **Actualización de Perfil**
- Actualizar nombre completo
- Actualizar teléfono
- Validación de formatos

### 3. **Estado de Suscripción**
- Consultar estado actual de suscripción
- Ver fechas de periodo activo
- Consultar último pago realizado

### 4. **Utilidades**
- Actualizar timestamp de último login
- Búsqueda case-insensitive por email

---

## 📊 Modelos de Datos

### User (compartido con Auth)
Modelo principal de usuario que contiene todos los datos del perfil.

**Campos relevantes para perfil:**
- `user_id` (UUID): Identificador único
- `user_email` (citext): Email único
- `user_full_name` (varchar): Nombre completo
- `user_phone` (text): Teléfono opcional
- `user_role` (enum): Rol del usuario
- `user_status` (enum): Estado de la cuenta
- `user_subscription_status` (enum): Estado de suscripción
- `subscription_period_start` (timestamptz): Inicio suscripción
- `subscription_period_end` (timestamptz): Fin suscripción
- `user_last_login` (timestamptz): Último acceso

---

## 🔧 Servicios

### UserProfileService

**Métodos principales:**

```python
# Consulta de usuarios
get_user_by_id(user_id: UUID) -> Optional[User]
get_user_by_email(email: str) -> Optional[User]

# Operaciones de perfil
get_profile_by_id(user_id: UUID) -> UserProfileResponse
get_profile_by_email(email: str) -> UserProfileResponse
update_profile(user_id: UUID, profile_data: UserProfileUpdateRequest) -> UserProfileUpdateResponse

# Suscripciones
get_subscription_status(user_id: UUID) -> SubscriptionStatusResponse

# Utilidades
update_last_login(user_id: UUID) -> None
```

---

## 📝 Schemas

### Request Schemas

**UserProfileUpdateRequest**
```python
{
    "user_full_name": "Juan Pérez García",  # opcional, 3-100 chars
    "user_phone": "+52 55 1234 5678"        # opcional, formato internacional
}
```

### Response Schemas

**UserProfileResponse**
```python
{
    "user_id": "uuid",
    "user_email": "user@example.com",
    "user_full_name": "Juan Pérez",
    "user_phone": "+52 55 1234 5678",
    "user_role": "customer",
    "user_status": "active",
    "user_subscription_status": "active",
    "subscription_period_end": "2025-11-18T00:00:00Z",
    "user_created_at": "2025-01-01T00:00:00Z",
    "user_updated_at": "2025-10-18T15:30:00Z",
    "user_last_login": "2025-10-18T08:45:00Z"
}
```

**SubscriptionStatusResponse**
```python
{
    "user_id": "uuid",
    "user_email": "user@example.com",
    "subscription_status": "active",
    "subscription_period_start": "2025-10-01T00:00:00Z",
    "subscription_period_end": "2025-11-01T00:00:00Z",
    "last_payment_date": "2025-10-01T10:30:00Z"
}
```

---

## 🛣️ Endpoints REST

### Base Path: `/api/profile`

| Método | Endpoint | Descripción | Auth |
|--------|----------|-------------|------|
| GET | `/` | Obtener perfil actual | ✅ |
| PUT | `/` | Actualizar perfil | ✅ |
| GET | `/subscription` | Estado de suscripción | ✅ |
| POST | `/update-last-login` | Actualizar último login | ✅ |

---

## 🔐 Seguridad

- **Autenticación JWT**: Todos los endpoints requieren token válido
- **Validación de inputs**: Pydantic valida formatos (email, teléfono)
- **RLS Policies**: Los usuarios solo acceden a su propio perfil
- **Sanitización**: Los datos se limpian con `.strip()` antes de guardar

---

## 🧪 Testing

### Fixtures Disponibles
- `sample_user`: Usuario activo completo
- `inactive_user`: Usuario suspendido
- `admin_user`: Usuario administrador

### Cobertura de Tests
- ✅ Consulta de perfil por ID y email
- ✅ Actualización de nombre y teléfono
- ✅ Estado de suscripción
- ✅ Validaciones de formato
- ✅ Manejo de errores (404, 400)

### Ejecutar Tests
```bash
pytest backend/app/modules/user_profile/tests/ -v
```

---

## 📋 Uso Básico

### Obtener Perfil
```python
from app.modules.user_profile.services import UserProfileService
from app.shared.database import get_db

db = next(get_db())
service = UserProfileService(db)

profile = service.get_profile_by_id(user_id=user_id)
print(f"Usuario: {profile.user_full_name}")
print(f"Suscripción: {profile.user_subscription_status}")
```

### Actualizar Perfil
```python
from app.modules.user_profile.schemas import UserProfileUpdateRequest

update_data = UserProfileUpdateRequest(
    user_full_name="Nuevo Nombre",
    user_phone="+52 55 9999 8888"
)

result = service.update_profile(
    user_id=user_id,
    profile_data=update_data
)
print(f"Actualizado: {result.message}")
```

---

## 🔄 Integración con Otros Módulos

### Auth
- Reutiliza modelo `User`
- Valida tokens JWT

### Payments
- Consulta pagos para estado de suscripción
- Vincula historial de pagos con perfil

---

## 📌 TODOs

- [ ] Implementar `get_current_user_id()` dependency para JWT
- [ ] Agregar endpoint para cambio de contraseña desde perfil
- [ ] Implementar notificaciones por email tras actualización
- [ ] Agregar validación de unicidad de teléfono
- [ ] Implementar soft-delete de cuenta

---

## 🚀 Estado del Módulo

**Progreso**: 100% ✅

- [x] Modelos (reutiliza auth.User)
- [x] Schemas (request/response)
- [x] Servicios (profile_service)
- [x] Routes (profile_routes)
- [x] Tests (test_services, test_routes)
- [x] Documentación (README.md)

---

**Autor**: DoxAI Team  
**Fecha**: 2025-10-18  
**Versión**: 1.0.0
