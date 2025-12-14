# Módulo `projects/` – Gestión de Proyectos RAG

Este módulo implementa toda la funcionalidad relacionada con la gestión de proyectos RAG (Retrieval-Augmented Generation) en la plataforma DoxAI.

---

## 📁 Estructura

```
projects/
├── models/          # Modelos ORM (Project, ProjectActivity)
├── schemas/         # Schemas Pydantic de request/response
├── services/        # Lógica de negocio de proyectos
├── routes/          # Endpoints REST API
├── tests/           # Tests unitarios y de integración
└── README.md        # Este archivo
```

---

## 🎯 Funcionalidades

### 1. **Gestión de Proyectos**
- Crear proyectos con nombre y descripción
- Generar slug único automáticamente
- Actualizar descripción
- Validar unicidad de nombres por usuario

### 2. **Workflow de Fases**
- Sistema de fases del proyecto (CREATED → UPLOADING → PROCESSING → READY → ERROR → ARCHIVED)
- Avanzar a la siguiente fase
- Retroceder a la fase anterior
- Validaciones de transición

### 3. **Estado del Proyecto**
- Cerrar proyectos (marca como completados)
- Archivar proyectos (soft delete)
- Filtrar por estado (activo/cerrado/archivado)

### 4. **Auditoría y Actividad**
- Registro automático de todas las acciones
- Historial completo de cambios
- Metadata JSON para contexto adicional
- Filtrado por tipo de acción

---

## 📊 Modelos de Datos

### Project

**Tabla:** `projects`

**Campos principales:**
- `project_id` (UUID): Identificador único
- `user_id` (UUID): Propietario del proyecto
- `project_name` (varchar): Nombre del proyecto
- `project_slug` (varchar): Slug único para URLs
- `project_description` (text): Descripción opcional
- `project_phase` (enum): Fase actual del workflow
- `project_is_closed` (boolean): Si está cerrado
- `project_is_archived` (boolean): Si está archivado
- `project_tags` (array): Tags opcionales
- `project_created_at` (timestamptz): Fecha de creación
- `project_updated_at` (timestamptz): Última actualización

**Fases disponibles:**
```python
class ProjectPhase(StrEnum):
    CREATED = "CREATED"          # Proyecto recién creado
    UPLOADING = "UPLOADING"      # Subiendo archivos
    PROCESSING = "PROCESSING"    # Procesando documentos
    READY = "READY"              # Listo para usar
    ERROR = "ERROR"              # Error en procesamiento
    ARCHIVED = "ARCHIVED"        # Archivado
```

### ProjectActivity

**Tabla:** `project_activity`

**Campos principales:**
- `project_activity_id` (UUID): ID de la actividad
- `project_id` (UUID): Proyecto relacionado
- `user_id` (UUID): Usuario que realizó la acción
- `project_action_type` (varchar): Tipo de acción
- `project_action_details` (text): Detalles descriptivos
- `project_action_metadata` (jsonb): Metadata adicional
- `project_action_created_at` (timestamptz): Timestamp

**Tipos de acción comunes:**
- `CREATED`: Proyecto creado
- `DESCRIPTION_UPDATED`: Descripción actualizada
- `PHASE_ADVANCED`: Fase avanzada
- `PHASE_ROLLBACK`: Fase retrocedida
- `PROJECT_CLOSED`: Proyecto cerrado
- `PROJECT_ARCHIVED`: Proyecto archivado

---

## 🔧 Servicios

### ProjectService

**Métodos principales:**

```python
# Creación
create_project(user_id, user_email, data) -> ProjectRead

# Consulta
get_project_by_id(project_id, user_id) -> ProjectRead
get_projects_by_user(user_id, include_archived, include_closed) -> List[ProjectRead]
get_active_projects(user_id) -> List[ProjectRead]
get_closed_projects(user_id) -> List[ProjectRead]

# Actualización
update_description(project_id, user_id, new_description) -> ProjectRead

# Fases
advance_phase(project_id, user_id) -> ProjectRead
rollback_phase(project_id, user_id) -> ProjectRead

# Estado
close_project(project_id, user_id) -> ProjectRead
archive_project(project_id, user_id) -> ProjectRead
```

### ProjectActivityService

**Métodos principales:**

```python
# Registro
create_activity(data: ProjectActivityCreate) -> ProjectActivityResponse

# Consulta
get_project_activities(project_id, action_type, limit) -> List[ProjectActivityResponse]
get_user_recent_activities(user_id, limit) -> List[ProjectActivityResponse]
```

---

## 📝 Schemas

### Request Schemas

**ProjectCreate**
```python
{
    "project_name": "Análisis Propuesta Q4 2025",
    "project_description": "Evaluación técnica de licitación"
}
```

**ProjectUpdateRequest**
```python
{
    "project_description": "Nueva descripción actualizada"
}
```

### Response Schemas

**ProjectRead**
```python
{
    "project_id": "uuid",
    "user_id": "uuid",
    "user_email": "user@example.com",
    "project_name": "Mi Proyecto",
    "project_slug": "mi-proyecto",
    "project_description": "Descripción",
    "project_phase": "CREATED",
    "project_is_archived": false,
    "project_is_closed": false,
    "project_tags": ["tag1", "tag2"],
    "project_created_at": "2025-10-18T10:00:00Z",
    "project_updated_at": "2025-10-18T15:30:00Z",
    "project_archived_at": null,
    "project_closed_at": null
}
```

**ProjectActivityResponse**
```python
{
    "project_activity_id": "uuid",
    "project_id": "uuid",
    "user_id": "uuid",
    "user_email": "user@example.com",
    "project_action_type": "CREATED",
    "project_action_details": "Proyecto creado",
    "project_action_metadata": {"initial_phase": "CREATED"},
    "project_action_created_at": "2025-10-18T10:00:00Z"
}
```

---

## 🛣️ Endpoints REST

### Base Path: `/api/projects`

| Método | Endpoint | Descripción | Auth |
|--------|----------|-------------|------|
| POST | `/` | Crear proyecto | ✅ |
| GET | `/` | Listar proyectos | ✅ |
| GET | `/active` | Proyectos activos | ✅ |
| GET | `/closed` | Proyectos cerrados | ✅ |
| GET | `/{id}` | Obtener proyecto | ✅ |
| PUT | `/{id}` | Actualizar descripción | ✅ |
| POST | `/{id}/close` | Cerrar proyecto | ✅ |
| POST | `/{id}/archive` | Archivar proyecto | ✅ |
| POST | `/{id}/advance-phase` | Avanzar fase | ✅ |
| POST | `/{id}/rollback-phase` | Retroceder fase | ✅ |
| GET | `/{id}/activity` | Historial de actividad | ✅ |

---

## 🔐 Seguridad

- **Autenticación JWT**: Todos los endpoints requieren token válido
- **Validación de pertenencia**: Los usuarios solo acceden a sus propios proyectos
- **RLS Policies**: Row Level Security en base de datos
- **Slug único**: Previene colisiones de nombres
- **Auditoría completa**: Todas las acciones quedan registradas

---

## 🧪 Testing

### Fixtures Disponibles
- `sample_user`: Usuario propietario de proyectos
- `sample_project`: Proyecto activo de prueba
- `closed_project`: Proyecto cerrado
- `archived_project`: Proyecto archivado
- `sample_activity`: Actividad de prueba

### Cobertura de Tests
- ✅ Creación de proyectos
- ✅ Validación de nombres duplicados
- ✅ Consulta por ID, usuario, estado
- ✅ Actualización de descripción
- ✅ Gestión de fases (avanzar/retroceder)
- ✅ Cierre y archivo de proyectos
- ✅ Validación de permisos (403/404)
- ✅ Registro y consulta de actividades

### Ejecutar Tests
```bash
pytest backend/app/modules/projects/tests/ -v
```

---

## 📋 Uso Básico

### Crear Proyecto
```python
from app.modules.projects.services import ProjectService
from app.modules.projects.schemas import ProjectCreate
from app.shared.database import get_db

db = next(get_db())
service = ProjectService(db)

project_data = ProjectCreate(
    project_name="Mi Nuevo Proyecto",
    project_description="Análisis de documentos técnicos"
)

project = service.create_project(
    user_id=user_id,
    user_email="user@example.com",
    data=project_data
)

print(f"Proyecto creado: {project.project_id}")
print(f"Slug: {project.project_slug}")
```

### Avanzar Fase
```python
project = service.advance_phase(
    project_id=project_id,
    user_id=user_id
)

print(f"Nueva fase: {project.project_phase}")
```

### Consultar Actividades
```python
from app.modules.projects.services import ProjectActivityService

activity_service = ProjectActivityService(db)

activities = activity_service.get_project_activities(
    project_id=project_id,
    limit=50
)

for activity in activities:
    print(f"{activity.project_action_created_at}: {activity.project_action_type}")
```

---

## 🔄 Integración con Otros Módulos

### Auth
- Valida pertenencia del proyecto al usuario
- Usa JWT para autenticación

### Files (Separado)
- Los archivos se gestionan en módulo independiente
- Referencia proyectos via `project_id`

### RAG (Futuro)
- Procesamiento de documentos por fase
- Indexación vectorial en fase PROCESSING

---

## 📌 TODOs

- [ ] Implementar `get_current_user_id()` dependency para JWT
- [ ] Agregar límites de proyectos por plan de usuario
- [ ] Implementar búsqueda por nombre/tags
- [ ] Agregar estadísticas del proyecto (archivos, tokens, etc.)
- [ ] Implementar notificaciones de cambio de fase
- [ ] Agregar export de historial de actividades

---

## 🚀 Estado del Módulo

**Progreso**: 100% ✅

- [x] Modelos (Project, ProjectActivity)
- [x] Schemas (request/response completos)
- [x] Servicios (ProjectService, ProjectActivityService)
- [x] Routes (11 endpoints REST)
- [x] Tests (test_services, test_routes)
- [x] Documentación (README.md)

---

**Autor**: DoxAI Team  
**Fecha**: 2025-10-18  
**Versión**: 1.0.0
