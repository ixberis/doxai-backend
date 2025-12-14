# Módulo `files/` – Gestión de Archivos

Este módulo implementa toda la funcionalidad relacionada con la gestión de archivos en la plataforma DoxAI, incluyendo archivos de entrada (input files) y archivos de salida (product files).

---

## 📁 Estructura

```
files/
├── models/              # Modelos ORM de archivos
│   ├── input_file_models.py           # Archivos de entrada
│   ├── input_file_metadata_models.py  # Metadatos de entrada
│   ├── product_file_models.py         # Archivos generados
│   ├── product_file_metadata_models.py # Metadatos de salida
│   └── product_file_activity_models.py # Actividad de archivos
├── schemas/             # Schemas Pydantic
│   ├── input_file_schemas.py
│   ├── product_file_schemas.py
│   └── ...
├── services/            # Lógica de negocio
│   ├── input_file_service.py
│   ├── product_file_service.py
│   ├── storage/         # Gestión de Supabase Storage
│   └── converters/      # Conversión de documentos
├── routes/              # Endpoints REST API
├── tests/               # Tests unitarios
└── README.md            # Este archivo
```

---

## 🎯 Funcionalidades

### 1. **Archivos de Entrada (Input Files)**
- Carga de archivos por parte del usuario
- Validación de tipo y tamaño
- Storage en Supabase Storage
- Clasificación automática de documentos
- Detección de idioma
- Procesamiento y extracción de contenido
- Metadatos técnicos (hash, status, errores)

### 2. **Archivos de Salida (Product Files)**
- Generación de archivos por el sistema
- Versionado de documentos generados
- Asociación con fases del proyecto
- Metadatos de revisión y calidad
- Auditoría de actividades

### 3. **Storage y Procesamiento**
- Integración con Supabase Storage
- Organización por proyecto y usuario
- Conversión de formatos (PDF, DOCX, etc.)
- Extracción de texto e imágenes
- Generación de thumbnails

---

## 📊 Modelos de Datos

### InputFile

**Tabla:** `input_files`

**Campos principales:**
- `input_file_id` (UUID): Identificador único
- `project_id` (UUID): Proyecto al que pertenece
- `user_email` (citext): Email del propietario
- `input_file_uploaded_by` (UUID): Usuario que subió el archivo
- `input_file_name` (varchar): Nombre almacenado
- `input_file_original_name` (varchar): Nombre original
- `input_file_type` (enum): Tipo de archivo (PDF, DOCX, etc.)
- `input_file_category` (enum): Categoría (INPUT_FILE)
- `input_file_class` (enum): Clasificación del documento
- `input_file_language` (enum): Idioma detectado
- `input_file_size` (int): Tamaño en bytes
- `input_file_storage_path` (text): Ruta en Storage
- `input_file_status` (enum): Estado de procesamiento
- `input_file_is_active` (bool): Si está activo
- `input_file_is_archived` (bool): Si está archivado
- `input_file_uploaded_at` (timestamptz): Fecha de carga

**Clasificaciones disponibles:**
```python
class InputFileClass(StrEnum):
    TERMINOS_REFERENCIA = "TERMINOS_REFERENCIA"
    PROPUESTA_TECNICA = "PROPUESTA_TECNICA"
    PROPUESTA_ECONOMICA = "PROPUESTA_ECONOMICA"
    ANEXOS_TECNICOS = "ANEXOS_TECNICOS"
    OTROS_DOCUMENTOS = "OTROS_DOCUMENTOS"
```

**Estados de procesamiento:**
```python
class InputProcessingStatus(StrEnum):
    PENDING = "INPUT_FILE_PENDING"
    PROCESSING = "INPUT_FILE_PROCESSING"
    PROCESSED = "INPUT_FILE_PROCESSED"
    FAILED = "INPUT_FILE_FAILED"
```

### InputFileMetadata

**Tabla:** `input_file_metadata`

**Campos principales:**
- `input_file_metadata_id` (UUID): ID de metadata
- `input_file_id` (UUID): Archivo relacionado (1:1)
- `input_file_validation_status` (enum): Estado de validación
- `input_file_processed_at` (datetime): Fecha de procesamiento
- `input_file_hash_checksum` (varchar): Hash SHA-256
- `input_file_parser_version` (varchar): Versión del parser
- `input_file_error_message` (text): Errores de procesamiento

### ProductFile

**Tabla:** `product_files`

**Campos principales:**
- `product_file_id` (UUID): Identificador único
- `project_id` (UUID): Proyecto relacionado
- `product_file_generated_by` (UUID): Usuario generador
- `product_file_type` (enum): Tipo de archivo producto
- `product_file_generation_phase` (enum): Fase de generación
- `product_file_version` (enum): Versión del documento
- `product_file_generated_at` (timestamptz): Fecha de generación

---

## 🔧 Servicios

### InputFileService

**Métodos principales:**

```python
# Upload
upload_input_file(project_id, project_slug, user_id, email, file_data, file_obj) -> InputFileResponse

# Listado
list_input_files(project_id, file_class, search, sort_by, sort_order, page, page_size) -> List[InputFileResponse]

# Consulta
get_input_file_by_id(file_id) -> InputFileResponse
download_input_file(file_id, project_slug) -> bytes

# Actualización
update_input_file(file_id, update_data) -> InputFileResponse

# Eliminación
delete_input_file(file_id, project_slug) -> None
```

### ProductFileService

**Métodos principales:**

```python
# Creación
create_product_file(project_id, file_data) -> ProductFileResponse

# Listado
list_product_files(project_id, file_type, page, page_size) -> List[ProductFileResponse]

# Consulta
get_product_file_by_id(file_id) -> ProductFileResponse
download_product_file(file_id, project_slug) -> bytes

# Gestión
archive_product_file(file_id) -> ProductFileResponse
delete_product_file(file_id, project_slug) -> None
```

---

## 📝 Schemas

### Request Schemas

**InputFileUpload**
```python
{
    "input_file_name": "documento-tecnico.pdf",
    "input_file_original_name": "Propuesta Técnica.pdf",
    "input_file_type": "PDF",
    "input_file_category": "INPUT_FILE",
    "input_file_class": "PROPUESTA_TECNICA",
    "input_file_language": "ES"
}
```

**InputFileUpdate**
```python
{
    "input_file_class": "ANEXOS_TECNICOS",
    "input_file_language": "EN"
}
```

### Response Schemas

**InputFileResponse**
```python
{
    "input_file_id": "uuid",
    "project_id": "uuid",
    "user_email": "user@example.com",
    "input_file_uploaded_by": "uuid",
    "input_file_name": "documento-tecnico.pdf",
    "input_file_original_name": "Propuesta Técnica.pdf",
    "input_file_type": "PDF",
    "input_file_category": "INPUT_FILE",
    "input_file_class": "PROPUESTA_TECNICA",
    "input_file_mime_type": "application/pdf",
    "input_file_size": 1024000,
    "input_file_storage_path": "projects/user-id/project-slug/input/...",
    "input_file_language": "ES",
    "input_file_status": "INPUT_FILE_PROCESSED",
    "input_file_is_active": true,
    "input_file_is_archived": false,
    "input_file_uploaded_at": "2025-10-18T10:00:00Z"
}
```

---

## 🛣️ Endpoints REST

### Input Files: `/api/projects/{project_id}/input-files`

| Método | Endpoint | Descripción | Auth |
|--------|----------|-------------|------|
| POST | `/upload` | Subir archivo | ✅ |
| GET | `/` | Listar archivos | ✅ |
| GET | `/{file_id}` | Obtener archivo | ✅ |
| GET | `/{file_id}/download` | Descargar archivo | ✅ |
| PUT | `/{file_id}` | Actualizar metadata | ✅ |
| DELETE | `/{file_id}` | Eliminar archivo | ✅ |

### Product Files: `/api/projects/{project_id}/product-files`

| Método | Endpoint | Descripción | Auth |
|--------|----------|-------------|------|
| POST | `/` | Crear archivo producto | ✅ |
| GET | `/` | Listar archivos | ✅ |
| GET | `/{file_id}` | Obtener archivo | ✅ |
| GET | `/{file_id}/download` | Descargar archivo | ✅ |
| POST | `/{file_id}/archive` | Archivar archivo | ✅ |
| DELETE | `/{file_id}` | Eliminar archivo | ✅ |

---

## 🔐 Seguridad

- **Autenticación JWT**: Todos los endpoints requieren token válido
- **Validación de pertenencia**: Los usuarios solo acceden a archivos de sus proyectos
- **Validación de tipo**: Solo tipos de archivo permitidos
- **Límites de tamaño**: Máximo 20MB por archivo (configurable)
- **RLS en Storage**: Políticas de seguridad en Supabase Storage
- **Hash checksum**: Integridad de archivos

---

## 🧪 Testing

### Fixtures Disponibles
- `sample_input_file`: Archivo de entrada de prueba
- `sample_product_file`: Archivo de salida de prueba
- `sample_metadata`: Metadatos de prueba

### Cobertura de Tests
- ✅ Carga de archivos
- ✅ Validación de tipo y tamaño
- ✅ Detección de idioma
- ✅ Listado con filtros
- ✅ Descarga de archivos
- ✅ Actualización de metadatos
- ✅ Eliminación completa

### Ejecutar Tests
```bash
pytest backend/app/modules/files/tests/ -v
```

---

## 📋 Uso Básico

### Subir Archivo
```python
from app.modules.files.services import InputFileService
from app.modules.files.schemas import InputFileUpload

service = InputFileService(db)

file_data = InputFileUpload(
    input_file_name="propuesta.pdf",
    input_file_original_name="Propuesta Técnica.pdf",
    input_file_type=FileType.PDF,
    input_file_category=FileCategory.INPUT_FILE,
    input_file_class=InputFileClass.PROPUESTA_TECNICA,
    input_file_language=Language.ES
)

file_response = await service.upload_input_file(
    project_id=project_id,
    project_slug="mi-proyecto",
    user_id=user_id,
    email="user@example.com",
    file_data=file_data,
    file_obj=upload_file  # FastAPI UploadFile
)
```

### Listar Archivos
```python
files = service.list_input_files(
    project_id=project_id,
    file_class=InputFileClass.PROPUESTA_TECNICA,
    search="propuesta",
    sort_by="uploaded_at",
    sort_order="desc",
    page=1,
    page_size=20
)
```

---

## 🔄 Integración con Otros Módulos

### Projects
- Los archivos pertenecen a proyectos específicos
- Organización por `project_slug` en Storage

### Storage (Supabase)
- Almacenamiento en buckets organizados
- RLS policies para seguridad
- Paths: `projects/{user_id}/{project_slug}/{input|product}/`

### RAG (Futuro)
- Procesamiento de archivos para indexación vectorial
- Extracción de texto para embeddings

---

## 📌 TODOs

- [ ] Implementar bulk upload de archivos
- [ ] Agregar preview de documentos
- [ ] Implementar OCR para documentos escaneados
- [ ] Agregar compresión automática de imágenes
- [ ] Implementar versionado de archivos
- [ ] Agregar estadísticas de uso de storage
- [ ] Implementar cleanup de archivos huérfanos

---

## 🚀 Estado del Módulo

**Progreso**: 60% ⏳

- [x] Modelos (InputFile, ProductFile, Metadatos)
- [x] Schemas (request/response completos)
- [x] Servicios core (InputFileService, ProductFileService)
- [x] Storage integration (Supabase)
- [ ] Routes consolidadas (parcial)
- [ ] Tests unitarios (parcial)
- [x] Documentación (README.md)

---

**Autor**: DoxAI Team  
**Fecha**: 2025-10-18  
**Versión**: 1.0.0  
**Status**: En migración - 60% completado
