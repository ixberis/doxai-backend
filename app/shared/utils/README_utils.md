
# backend/app/utils/README_utils.md

# 🛠️ Módulo utils/

El módulo `utils/` centraliza utilidades generales y transversales utilizadas en todo el backend de DoxAI. Incluye funciones para seguridad, validación de archivos, generación de slugs únicos, manejo de tokens, validación de contraseñas, reCAPTCHA, modelos base reutilizables, gestión de fases de proyectos y utilidades para Supabase y archivos ZIP.

---

## 📁 Estructura

### 🔐 Seguridad y autenticación

- `security.py`: Hasheo y verificación de contraseñas con bcrypt.
- `jwt_utils.py`: Generación y validación de tokens JWT con tipos personalizados (`activation`, `access`, etc.).
- `recaptcha.py`: Verificación de tokens reCAPTCHA v2 desde el backend mediante la API de Google.
- `password_validation.py`: Validación de complejidad de contraseñas.

### ⚙️ Utilidades para backend

- `base_models.py`: Define `UTF8SafeModel` (modelo base para Pydantic) y reexporta `EmailStr`, `Field`.
- `slug_utils.py`: Genera slugs únicos y seguros para nombres de proyectos (uso en creación de proyectos).
- `file_validation_utils.py`: Valida extensiones y tamaños de archivos (según entorno).
- `project_phase_utils.py`: Gestiona el flujo de fases del modelo RAG como máquina de estados finitos.
- `supabase_client.py`: Cliente centralizado para operaciones con Supabase (si aplica).
- `zip_utils.py`: Funciones para comprimir y descomprimir archivos ZIP.
- `sqlalchemy_typing.py`: Tipos y anotaciones para uso con SQLAlchemy.

---

## ✅ Funciones clave disponibles

- `hash_password(password)`
- `verify_password(plain, hashed)`
- `validate_password_complexity(password)`
- `create_access_token(data, ..., token_type)`
- `decode_token(token)`
- `verify_token_type(token, expected_type)`
- `verify_recaptcha(token)`
- `generate_unique_slug(db, project_name)`
- `validate_file_type_and_size(file_name: str, file_size_mb: float)`
- `get_next_phase(current_phase: str) -> Optional[str]`
- `is_valid_transition(current_phase: str, next_phase: str) -> bool`
- `UTF8SafeModel`, `EmailStr`, `Field`

---

## 🧩 Dependencias internas

Este módulo es utilizado en:

- Registro, login y perfil de usuarios
- Carga, validación y procesamiento de archivos
- Creación y activación de proyectos
- Validación de flujos del modelo RAG
- Seguridad de formularios y sesiones

---

## 🧪 Consideraciones para desarrollo

- Las validaciones de archivos dependen de variables de entorno (`MAX_FILE_SIZE_MB`, `ALLOWED_FILE_TYPES`)
- El flujo de fases puede modificarse extendiendo el diccionario `PHASE_TRANSITIONS` en `project_phase_utils.py`

---

## 👤 Autoría

Ixchel Beristain  
Fecha de creación: 31/05/2025  
Última actualización: 04/07/2025

