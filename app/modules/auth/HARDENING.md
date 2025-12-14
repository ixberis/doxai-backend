# Auth Backend Hardening - DoxAI

## 📋 Resumen

Este documento describe las mejoras de seguridad y robustez implementadas en el módulo de autenticación de DoxAI, completando las piezas "reales" de JWT, email, captcha, CORS, sesiones/refresh y rate limiting.

## ✅ Cambios Implementados

### 1. JWT Real en Runtime

**Archivos modificados:**
- `backend/app/shared/config/settings_base.py` - Propiedades de compatibilidad agregadas
- `backend/app/modules/auth/services/token_issuer_service.py` - Ya existía, funcional

**Propiedades de compatibilidad agregadas:**
```python
@computed_field
@property
def jwt_secret(self) -> str:
    """Alias: jwt_secret_key -> jwt_secret"""
    return self.jwt_secret_key.get_secret_value()

@computed_field
@property
def RECAPTCHA_ENABLED(self) -> bool:
    """Alias: recaptcha_enabled -> RECAPTCHA_ENABLED"""
    return self.recaptcha_enabled

@computed_field
@property
def recaptcha_secret_key(self) -> str:
    """Alias: recaptcha_secret -> recaptcha_secret_key"""
    if self.recaptcha_secret:
        return self.recaptcha_secret.get_secret_value()
    return ""
```

**Variables de entorno utilizadas:**
- `JWT_SECRET_KEY` / `JWT_SECRET` - Clave secreta para firmar tokens
- `JWT_ALGORITHM` - Algoritmo de firma (HS256/RS256)
- `ACCESS_TOKEN_EXPIRE_MINUTES` - Duración del access token (default: 60 min)
- `REFRESH_TOKEN_EXPIRE_MINUTES` - Duración del refresh token (default: 1440 min / 24h)
- `ACTIVATION_TOKEN_EXPIRE_MINUTES` - Duración del token de activación (default: 60 min)

**Comportamiento:**
- En runtime: Usa `TokenIssuerService` con las variables del `.env`
- En tests: Mantiene stubs inertes para no romper suite existente
- La fachada `get_auth_facade` inyecta el servicio real automáticamente

### 2. Email Sender Real

**Archivos:**
- `backend/app/shared/integrations/email_sender.py` - Ya implementado
- `backend/app/modules/auth/services/auth_service.py` - Integración completa

**Variables de entorno utilizadas:**
- `EMAIL_MODE` - Modo de email: `console` (desarrollo) o `smtp` (producción)
- `EMAIL_SERVER` - Servidor SMTP
- `EMAIL_PORT` - Puerto SMTP (default: 465)
- `EMAIL_USE_SSL` - Usar SSL (default: true)
- `EMAIL_USERNAME` - Usuario SMTP
- `EMAIL_PASSWORD` - Contraseña SMTP
- `EMAIL_FROM` - Dirección de origen
- `EMAIL_TEMPLATES_DIR` - Directorio de templates (opcional)
- `EMAIL_TIMEOUT_SEC` - Timeout para envío (default: 8)

**Flujos implementados:**
- Activación de cuenta
- Reset de contraseña
- Email de bienvenida (tras activación)

### 3. reCAPTCHA Opcional

**Archivos:**
- `backend/app/shared/integrations/recaptcha_adapter.py` - Ya implementado
- `backend/app/modules/auth/services/auth_service.py` - Integración con bypass

**Variables de entorno utilizadas:**
- `RECAPTCHA_ENABLED` - Habilita/deshabilita verificación (true/false)
- `RECAPTCHA_SECRET` / `RECAPTCHA_SECRET_KEY` - Clave secreta de Google reCAPTCHA
- `RECAPTCHA_SITE_KEY` - Clave pública del sitio (para frontend)
- `RECAPTCHA_TIMEOUT_SEC` - Timeout para verificación (default: 8)

**Comportamiento:**
- Si `RECAPTCHA_ENABLED=false`, bypassa automáticamente
- Si `RECAPTCHA_ENABLED=true`, valida contra API de Google
- Soporta reCAPTCHA v2 y v3

### 4. CORS Backend

**Archivos:**
- `backend/app/shared/config/settings_base.py` - Método `get_cors_origins()`

**Variables de entorno utilizadas:**
- `CORS_ORIGINS` / `CORS_ALLOWED_ORIGINS` - Lista de orígenes permitidos separados por coma
- `FRONTEND_URL` - URL del frontend principal

**Ejemplo configuración:**
```bash
CORS_ORIGINS="http://localhost:3000,http://localhost:8080,https://app.doxai.com"
```

**Uso en middleware:**
```python
from app.shared.config.config_loader import get_settings

settings = get_settings()
origins = settings.get_cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 5. Login y Refresh Tokens

**Archivos nuevos:**
- `backend/app/modules/auth/services/login_attempt_service.py` - Rate limiting
- `backend/app/modules/auth/services/audit_service.py` - Auditoría de eventos

**Archivos modificados:**
- `backend/app/modules/auth/services/auth_service.py` - Login y refresh implementados

**Flujo de login:**
1. Verificar reCAPTCHA (si está habilitado)
2. Rate limiting por IP y email
3. Validar credenciales
4. Verificar cuenta activa
5. Generar access + refresh tokens
6. Auditar evento
7. Limpiar contadores de intentos fallidos

**Flujo de refresh:**
1. Validar refresh token y tipo
2. Extraer user_id del payload
3. Verificar usuario existe y está activo
4. Generar nuevos access + refresh tokens
5. Auditar evento

**Estrategia de tokens:**
- **Stateless**: Tokens JWT auto-contenidos
- **Sin revocación explícita**: Usar expiración corta en access tokens
- **Rotación de refresh tokens**: Se genera nuevo refresh en cada renovación
- **Preparado para storage**: Estructura lista para implementar lista negra o whitelist en Redis/DB

### 6. Rate Limiting para Login

**Archivo:**
- `backend/app/modules/auth/services/login_attempt_service.py`

**Variables de entorno utilizadas:**
- `LOGIN_ATTEMPTS_LIMIT` - Máximo de intentos fallidos (default: 5)
- `LOGIN_ATTEMPTS_TIME_WINDOW_MINUTES` - Ventana de tiempo en minutos (default: 15)
- `LOGIN_LOCKOUT_DURATION_MINUTES` - Duración del bloqueo tras exceder límite (default: 30)

**Características:**
- Rate limiting dual: por IP y por email
- Bloqueo temporal tras exceder límite
- Reseteo automático tras ventana de tiempo
- Implementación en memoria (stateless)
- Preparado para migrar a Redis en producción

**Ejemplo de uso:**
```python
from app.modules.auth.services.login_attempt_service import LoginAttemptService

service = LoginAttemptService()

# Verificar límite
service.check_rate_limit("192.168.1.1", "ip")  # Lanza 429 si excedió

# Registrar fallo
service.record_failed_attempt("192.168.1.1", "user@example.com")

# Login exitoso limpia contadores
service.record_successful_login("192.168.1.1", "user@example.com")
```

### 7. Auditoría Mínima

**Archivo:**
- `backend/app/modules/auth/services/audit_service.py`

**Eventos auditados:**
- `LOGIN_SUCCESS` - Login exitoso
- `LOGIN_FAILED` - Login fallido (credenciales inválidas)
- `LOGIN_BLOCKED` - Intento bloqueado por rate limit
- `REGISTER_SUCCESS` - Registro exitoso
- `ACTIVATION_SUCCESS` - Activación de cuenta exitosa
- `PASSWORD_RESET_REQUEST` - Solicitud de reset
- `PASSWORD_RESET_CONFIRM` - Confirmación de reset
- `REFRESH_TOKEN_SUCCESS` - Refresh de token exitoso

**Formato de logs:**
- JSON estructurado para facilitar parsing
- Emails ofuscados (solo primeros 3 chars + dominio)
- Timestamps en UTC ISO 8601
- Contexto completo: user_id, email, IP, user agent
- Nivel INFO para éxitos, WARNING para fallos

**Variables de entorno utilizadas:**
- `LOG_LEVEL` - Nivel de logging (DEBUG/INFO/WARNING/ERROR)
- `LOG_FORMAT` - Formato: `json`, `pretty`, `plain`

**Ejemplo de log:**
```json
{
  "timestamp": "2025-11-02T15:30:45.123456Z",
  "event_type": "login_success",
  "success": true,
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "email": "usu***@example.com",
  "ip_address": "192.168.1.1",
  "user_agent": "Mozilla/5.0..."
}
```

### 8. Tests Adicionales

**Archivos nuevos:**
- `backend/tests/modules/auth/services/test_login_attempt_service.py`
- `backend/tests/modules/auth/services/test_audit_service.py`

**Cobertura:**
- LoginAttemptService: inicialización, rate limiting, bloqueo, reset
- AuditService: ofuscación de emails, estructura de logs, helpers

## 🔐 Variables de Entorno - Resumen Completo

### Auth / JWT
```bash
JWT_SECRET_KEY=<mínimo 32 caracteres en producción>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_MINUTES=1440
ACTIVATION_TOKEN_EXPIRE_MINUTES=60
```

### reCAPTCHA
```bash
RECAPTCHA_ENABLED=false  # true en producción
RECAPTCHA_SECRET=<secret key de Google>
RECAPTCHA_SITE_KEY=<site key para frontend>
RECAPTCHA_TIMEOUT_SEC=8
```

### Email
```bash
EMAIL_MODE=console  # smtp en producción
EMAIL_SERVER=smtp.example.com
EMAIL_PORT=465
EMAIL_USE_SSL=true
EMAIL_USERNAME=<smtp user>
EMAIL_PASSWORD=<smtp password>
EMAIL_FROM=doxai@juvare.mx
EMAIL_TIMEOUT_SEC=8
```

### CORS
```bash
CORS_ORIGINS=http://localhost:3000,http://localhost:8080
FRONTEND_URL=http://localhost:8080
```

### Rate Limiting
```bash
LOGIN_ATTEMPTS_LIMIT=5
LOGIN_ATTEMPTS_TIME_WINDOW_MINUTES=15
LOGIN_LOCKOUT_DURATION_MINUTES=30
```

### Logging
```bash
LOG_LEVEL=INFO  # DEBUG en desarrollo
LOG_FORMAT=pretty  # json en producción
```

## 🧪 Ejecución de Tests

```bash
# Suite completa de auth
pytest -q tests/modules/auth

# Tests específicos de servicios nuevos
pytest -q tests/modules/auth/services/test_login_attempt_service.py
pytest -q tests/modules/auth/services/test_audit_service.py

# Tests de rutas (debe pasar 4/4)
pytest -q tests/modules/auth/routes
```

## 📊 Criterios de Aceptación

- [x] `pytest -q` pasa en verde (todos los tests existentes + nuevos)
- [x] Endpoints públicos intactos (contratos y OpenAPI)
- [x] `get_auth_facade` usa issuer real fuera de pytest
- [x] Email sender y reCAPTCHA respetan flags del `.env`
- [x] CORS lee orígenes del `.env`
- [x] Rate limiting de login activo y configurable
- [x] Auditoría implementada con logging estructurado JSON
- [x] Sin cambios en nombres de env keys existentes
- [x] Sin cambios en esquema de BD o RLS
- [x] Compatibilidad con tests existentes mantenida

## 🚀 No Objetivos (Pendientes para Futuro)

- Consola admin completa (rutas admin pueden quedar como stubs 501)
- Storage persistente de refresh tokens (preparado para Redis/DB)
- Revocación explícita de tokens (lista negra)
- Cambios al esquema de base de datos
- Migraciones de RLS policies

## 📝 Notas de Migración a Producción

### Redis para Rate Limiting
Actualmente, `LoginAttemptService` usa storage en memoria. Para producción distribuida:

1. Instalar Redis:
```bash
pip install redis aioredis
```

2. Configurar variable:
```bash
REDIS_URL=redis://localhost:6379/0
```

3. Reemplazar storage en `LoginAttemptService`:
```python
# Usar Redis en lugar de defaultdict
self._redis = aioredis.from_url(settings.redis_url)
```

### Rotación de Secrets
En producción, rotar periódicamente:
- `JWT_SECRET_KEY`: Cada 90 días
- `RECAPTCHA_SECRET`: Según políticas de Google
- `EMAIL_PASSWORD`: Cada 90 días

### Monitoreo
Configurar alertas para:
- Alta tasa de `LOGIN_BLOCKED` (posible ataque)
- Alta tasa de `LOGIN_FAILED` (credential stuffing)
- Picos en `PASSWORD_RESET_REQUEST` (posible enumeración)

## 🔗 Referencias

- [JWT Best Practices](https://tools.ietf.org/html/rfc8725)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [Google reCAPTCHA v3 Docs](https://developers.google.com/recaptcha/docs/v3)

---

**Autor:** DoxAI Team  
**Fecha:** 02/11/2025  
**Versión:** 1.0.0
