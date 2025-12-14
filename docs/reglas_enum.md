
A continuación las **mejores prácticas reconocidas** tanto en **Python (PEP 8 / PEP 435)** como en **ORMs como SQLAlchemy y bases relacionales como PostgreSQL**.

---

# 🧩 1. Estructura general del archivo Enum

Cada archivo `*_enum.py` debe contener:

1. Un **docstring descriptivo** (como los tuyos: ruta, descripción, autor, fecha).
2. Una **única clase Enum** principal.
3. Un **factory function** (como `as_pg_enum`) si se mapea a DB.
4. Una lista `__all__` clara con lo exportado.
5. (Opcional) un **footer estándar** de fin de archivo.

📘 Ejemplo base:

```python
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/enums/user_status_enum.py

Enum de estados de usuario.
Usado como tipo ENUM en PostgreSQL (user_status_enum).

Autor: Ixchel Beristain
Fecha: 23/10/2025
"""

from enum import Enum
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

class UserStatus(str, Enum):
    active = "active"
    inactive = "inactive"
    suspended = "suspended"

def as_pg_enum(name: str = "user_status_enum", native_enum: bool = False):
    return PG_ENUM(UserStatus, name=name, create_type=False, native_enum=native_enum)

__all__ = ["UserStatus", "as_pg_enum"]

# Fin del archivo backend/app/modules/auth/enums/user_status_enum.py
```

---

# ⚙️ 2. Convenciones de nombres (archivos, clases, valores, tipos)

| Elemento               | Recomendación                  | Ejemplo                             |
| ---------------------- | ------------------------------ | ----------------------------------- |
| **Archivo**            | snake_case + sufijo `_enum.py` | `user_role_enum.py`                 |
| **Clase Enum**         | PascalCase                     | `UserRole`                          |
| **Valores**            | minúsculas, tipo `str`         | `admin = "admin"`                   |
| **Nombre del tipo PG** | snake_case + sufijo `_enum`    | `user_role_enum`                    |
| **Factory function**   | `as_pg_enum` (o `pg_enum`)     | `as_pg_enum(name="user_role_enum")` |

🟢 Esto asegura consistencia y evita conflictos entre código, ORM y la base de datos.

---

# 🧱 3. Diseño de los valores

### ✅ Usar `str` y no `int`

* **Ventaja:** más legible y estable (no dependes del orden).
* `class UserStatus(str, Enum): active = "active"`
* Evita `IntEnum` salvo que tengas necesidad numérica explícita.

### ✅ Minúsculas en los valores

* Facilita uso en SQL (`WHERE user_status = 'active'`).
* Evita problemas de case sensitivity y serialización JSON.

### ❌ Evitar espacios, guiones o mayúsculas

* Si necesitas frases, usa `_` o camelCase (`"in_review"`, `"pendingPayment"`).

### ✅ Valores = claves

* Mantén `ACTIVE = "active"` (clave y valor coinciden).
* Así evitas confusión en validaciones o serializaciones.

---

# 🧭 4. Convenciones con SQLAlchemy y PostgreSQL

1. **Nombre del tipo en la BD**

   * Usa un nombre fijo (`user_status_enum`), sin depender del nombre del módulo.
   * Añade `create_type=False` si vas a manejar la creación por Alembic (evita duplicados).

2. **Factory `as_pg_enum`**

   * Es buena práctica crear un factory que devuelve el tipo SQLAlchemy:

     ```python
     def as_pg_enum(name="user_status_enum"):
         return PG_ENUM(UserStatus, name=name, create_type=False)
     ```
   * Así no tienes que importar `PG_ENUM` ni repetir configuración en los modelos.

3. **Control de migraciones (Alembic)**

   * Define los tipos antes de usarlos en modelos, o crea migraciones que los creen explícitamente.
   * Usa `alembic revision --autogenerate` con cuidado: si cambias valores, necesitarás un `ALTER TYPE`.

---

# 🧠 5. Documentación y consistencia

* **Describe cada Enum en el docstring:** propósito, uso, si mapea a DB, si se usa solo en validaciones.
* **Unifica formato de docstrings**.
* **Usa el mismo casing en toda la app** (p. ej., minúsculas en todos los valores).

---

# 🧩 6. Exposición pública de enums

### ✅ A través de `__init__.py`

Cada carpeta `enums/` debe tener un `__init__.py` que reexporte los enums oficiales:

```python
from .user_role_enum import UserRole, as_pg_enum as user_role_pg_enum
from .user_status_enum import UserStatus, as_pg_enum as user_status_pg_enum

__all__ = [
    "UserRole", "user_role_pg_enum",
    "UserStatus", "user_status_pg_enum",
]
```

Esto permite importar limpiamente:

```python
from app.modules.auth.enums import UserStatus, user_status_pg_enum
```

---

# 🔄 7. Cambios de valores o nombres (migraciones seguras)

Si cambias los valores de un Enum ya creado en DB:

1. Crea un `ALTER TYPE` manual en Alembic:

   ```sql
   ALTER TYPE user_status_enum ADD VALUE 'archived';
   ```
2. **Nunca elimines valores antiguos** directamente: PostgreSQL no lo permite sin recrear el tipo.
3. Documenta las versiones del Enum en tu changelog interno.

---

# 🧰 8. Errores comunes a evitar

| Error                                                   | Consecuencia                                        |
| ------------------------------------------------------- | --------------------------------------------------- |
| Usar `IntEnum` sin necesidad                            | Migraciones complejas y confusión de valores        |
| Usar valores en MAYÚSCULAS                              | Case-sensitive, rompe queries o serialización       |
| Duplicar nombres (`user_role_enum.py` y `role_enum.py`) | Confusión y tipos duplicados en DB                  |
| No fijar `name=` en `PG_ENUM`                           | Alembic crea tipos con nombres distintos cada vez   |
| No usar `create_type=False`                             | Alembic/SQLAlchemy intenta crear el tipo en runtime |
| Mezclar valores (minúsculas/mayúsculas)                 | Validaciones inconsistentes en la API               |

---

# 🏁 9. Plantilla recomendada para tus futuros enums

```python
# -*- coding: utf-8 -*-
"""
backend/app/modules/<modulo>/enums/<nombre>_enum.py

Descripción breve del Enum y su propósito.

Autor: Ixchel Beristain
Fecha: <dd/mm/yyyy>
"""

from enum import Enum
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

class <Nombre>(str, Enum):
    valor1 = "valor1"
    valor2 = "valor2"
    valor3 = "valor3"

def as_pg_enum(name: str = "<nombre>_enum", native_enum: bool = False):
    return PG_ENUM(<Nombre>, name=name, create_type=False, native_enum=native_enum)

__all__ = ["<Nombre>", "as_pg_enum"]

# Fin del archivo backend/app/modules/<modulo>/enums/<nombre>_enum.py
```

---

## ✅ En resumen — Reglas de oro

| Tema                   | Regla                                                  |
| ---------------------- | ------------------------------------------------------ |
| **Casing de valores**  | **minúsculas**                                         |
| **Tipo base**          | `str, Enum`                                            |
| **Archivo**            | snake_case + `_enum.py`                                |
| **Clase**              | PascalCase (`UserRole`)                                |
| **Tipo en DB**         | snake_case + `_enum`                                   |
| **Factory**            | `as_pg_enum()`                                         |
| **Docstring / Footer** | siempre presentes                                      |
| **Exports**            | definidos en `__all__` y reexportados en `__init__.py` |
| **Mantenibilidad**     | un enum por archivo; sin duplicados                    |


