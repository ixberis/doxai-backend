# Módulo RAG (Retrieval-Augmented Generation) - DoxAI v2

## 📋 Visión General

El módulo RAG es responsable de la **indexación semántica** de documentos en DoxAI v2. Transforma archivos cargados por usuarios en vectores consultables mediante embeddings, permitiendo búsqueda semántica y análisis avanzado de documentos.

### Pipeline de Indexación

El pipeline RAG procesa documentos a través de las siguientes fases secuenciales:

```
📄 Documento → 🔄 Convert → 🔍 OCR → ✂️ Chunk → 🧠 Embed → 🔗 Integrate → ✅ Ready
```

1. **Convert** (`RagPhase.convert`): Extrae texto del documento fuente
2. **OCR** (`RagPhase.ocr`): Aplica reconocimiento óptico si es necesario (imágenes, PDFs escaneados)
3. **Chunk** (`RagPhase.chunk`): Segmenta el texto en fragmentos procesables
4. **Embed** (`RagPhase.embed`): Genera vectores semánticos usando modelos de embeddings
5. **Integrate** (`RagPhase.integrate`): Valida e integra embeddings en el índice vectorial
6. **Ready** (`RagPhase.ready`): Marca el documento como listo para consultas semánticas

---

## 🏗️ Arquitectura Interna

El módulo sigue una arquitectura limpia en capas, alineada con el patrón v2 de DoxAI:

### Estructura de Directorios

```
backend/app/modules/rag/
├── enums/                    # Enumeraciones (RagPhase, RagJobPhase, RagJobStatus, etc.)
├── models/                   # Modelos ORM (RagJob, RagJobEvent, ChunkMetadata, DocumentEmbedding)
├── repositories/             # Capa de acceso a datos (rag_job_repository, chunk_repository, etc.)
├── services/                 # Lógica de dominio (IndexingService, ChunkingService, EmbeddingService)
├── facades/                  # Fachadas de integración (convert, ocr, chunk, embed, integrate, orchestrator)
├── routes/                   # Rutas HTTP (indexing, status, ocr, diagnostics, metrics)
├── schemas/                  # Schemas Pydantic (IndexingJobCreate, JobProgressResponse, etc.)
├── metrics/                  # Métricas y observabilidad (Prometheus, snapshots)
└── diagnostics/              # Vistas de diagnóstico SQL
```

### Flujo de Llamadas

```
HTTP Request (routes)
    ↓
Services (lógica de negocio)
    ↓
Facades (orquestación + integraciones externas)
    ↓
Repositories (acceso a DB)
    ↓
Database / External APIs (Azure, OpenAI, Storage)
```

**Principios clave:**
- **Async-first**: Todas las operaciones son asíncronas
- **Separación de capas**: Cada capa tiene responsabilidades claras
- **No queries directas**: Services y facades usan repositories, nunca SQL directo
- **Event sourcing**: Cada transición de fase registra eventos en `rag_job_events`

---

## 🔌 Integraciones Externas

### 1. Azure Document Intelligence (OCR)

**Propósito**: Extracción de texto de documentos con imágenes o PDFs escaneados.

**Cliente**: `app.shared.integrations.azure_document_intelligence.AzureDocumentIntelligenceClient`

**Configuración** (variables de entorno):
```bash
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://your-instance.cognitiveservices.azure.com
AZURE_DOCUMENT_INTELLIGENCE_KEY=your_api_key_here
```

**Uso**: La facade `run_ocr` en `ocr_facade.py` invoca el cliente cuando `needs_ocr=True`.

---

### 2. OpenAI Embeddings

**Propósito**: Generar vectores semánticos de texto (embeddings) para búsqueda vectorial.

**Cliente**: `app.shared.integrations.openai_embeddings_client.generate_embeddings`

**Configuración** (variables de entorno):
```bash
OPENAI_API_KEY=your_openai_api_key
OPENAI_EMBEDDING_MODEL=text-embedding-3-large  # Modelo por defecto
OPENAI_EMBEDDING_DIMENSION=1536                # Dimensión del vector
```

**Uso**: La facade `generate_embeddings_facade` en `embed_facade.py` genera vectores para cada chunk de texto.

**Idempotencia**: Antes de insertar embeddings, se verifica si ya existen para `(file_id, chunk_index, embedding_model)` evitando duplicados.

---

### 3. Supabase Storage

**Propósito**: Almacenamiento de archivos fuente, artefactos intermedios y caché del pipeline.

**Cliente**: `app.shared.storage.storage_io.get_storage_client` (AsyncStorageClient)

**Buckets utilizados**:
- **`users-files`**: Archivos originales cargados por usuarios (referenciados por `file_id`)
- **`rag-cache-jobs`**: Artefactos de conversión y resultados intermedios por job (`{job_id}/converted.txt`)
- **`rag-cache-pages`**: Cache de páginas OCR procesadas

**Uso en facades**:
- `convert_facade.py`: Lee de `users-files`, escribe texto convertido en `rag-cache-jobs`
- `ocr_facade.py`: Lee de `users-files`, guarda resultados OCR en `rag-cache-pages`

---

## 💳 Integración con Payments

El módulo RAG consume créditos del wallet del usuario por cada operación de indexación. La integración con Payments sigue el patrón de **reserva → consumo/liberación**:

### Flujo de Créditos

1. **Reserva (al iniciar job)**:
   - Se estima el costo en créditos: `base_cost + ocr_cost + embedding_cost`
   - Se llama a `reserve_credits` de `app.modules.payments.facades.reservations`
   - Se guarda el `reservation_id` asociado al job

2. **Consumo (al completar exitosamente)**:
   - Se calculan los créditos realmente usados (basado en chunks/embeddings generados)
   - Se llama a `consume_reserved_credits` para confirmar el gasto
   - Se actualiza el wallet del usuario

3. **Liberación (en caso de fallo o cancelación)**:
   - Se llama a `release_reservation` para devolver los créditos al wallet
   - No se cobra al usuario por jobs fallidos

### Entidades Clave

- **`UsageReservation`**: Representa una reserva temporal de créditos
- **`Wallet`**: Saldo de créditos del usuario
- **`CreditTransaction`**: Historial de movimientos (reserva, consumo, liberación)

**Archivo**: `backend/app/modules/rag/facades/orchestrator_facade.py` contiene la lógica de integración.

---

## 🌐 Endpoints Principales

### 1. Crear Job de Indexación

**Endpoint**: `POST /rag/projects/{project_id}/jobs/indexing`

**Request Body**:
```json
{
  "project_id": "uuid",
  "file_id": "uuid",
  "user_id": "uuid",
  "mime_type": "application/pdf",
  "needs_ocr": false
}
```

**Response** (`IndexingJobResponse`):
```json
{
  "job_id": "uuid",
  "project_id": "uuid",
  "started_by": "uuid",
  "phase": "queued",
  "created_at": "2025-11-28T10:00:00Z",
  "updated_at": "2025-11-28T10:00:00Z"
}
```

---

### 2. Consultar Progreso de Job

**Endpoint**: `GET /rag/jobs/{job_id}/progress`

**Response** (`JobProgressResponse`):
```json
{
  "job_id": "uuid",
  "project_id": "uuid",
  "file_id": "uuid",
  "phase": "embed",
  "status": "running",
  "progress_pct": 80,
  "started_at": "2025-11-28T10:00:00Z",
  "finished_at": null,
  "updated_at": "2025-11-28T10:05:00Z",
  "event_count": 12,
  "timeline": [
    {
      "phase": "convert",
      "message": "Text extraction completed",
      "progress_pct": 20,
      "created_at": "2025-11-28T10:01:00Z"
    },
    {
      "phase": "chunk",
      "message": "Document segmented into 45 chunks",
      "progress_pct": 60,
      "created_at": "2025-11-28T10:03:00Z"
    }
  ]
}
```

---

### 3. Listar Jobs de un Proyecto

**Endpoint**: `GET /rag/projects/{project_id}/jobs`

**Query Params**:
- `limit` (int, default: 50): Número máximo de jobs a devolver
- `offset` (int, default: 0): Offset para paginación

**Response**: Lista de `JobProgressResponse` (simplificada)

---

### 4. Estado de un Documento

**Endpoint**: `GET /rag/documents/{file_id}/status`

**Response** (`DocumentStatusResponse`):
```json
{
  "file_id": "uuid",
  "is_ready": true,
  "last_job_id": "uuid",
  "last_status": "completed",
  "last_phase": "ready",
  "active_embeddings_count": 45
}
```

---

## 🧪 Testing y Desarrollo

### Comandos de Test

```bash
# Ejecutar tests de repositorios (persistencia)
pytest backend/tests/modules/rag/repositories/ -v

# Ejecutar tests de services (lógica de dominio)
pytest backend/tests/modules/rag/services/ -v

# Ejecutar tests de facades (integraciones)
pytest backend/tests/modules/rag/facades/ -v

# Ejecutar tests de rutas HTTP
pytest backend/tests/modules/rag/routes/ -v

# Ejecutar tests de métricas
pytest backend/tests/modules/rag/routes/test_metrics_routes.py -v

# Ejecutar tests de diagnósticos SQL (requiere Postgres)
pytest backend/tests/modules/rag/diagnostics/ -v -m diagnostics_sql

# Suite completa del módulo RAG
pytest backend/tests/modules/rag/ -v --tb=short

# Test End-to-End (Auth → Projects → Files → RAG)
pytest backend/tests/integration/test_rag_e2e_pipeline.py -v
```

### Mocks en Tests

**⚠️ IMPORTANTE**: Los tests **NO** deben llamar servicios externos reales.

**Siempre mockear**:
- **Azure Document Intelligence**: `AzureDocumentIntelligenceClient`
- **OpenAI Embeddings**: `generate_embeddings`
- **Supabase Storage**: `AsyncStorageClient` (upload/download)
- **Payments** (opcional): Facades de reserva/consumo si es muy pesado

**Ejemplo de mock**:
```python
@pytest.fixture
def mock_openai_embeddings():
    with patch("app.shared.integrations.openai_embeddings_client.generate_embeddings") as mock_gen:
        mock_gen.return_value = [[0.1] * 1536, [0.2] * 1536]  # Vectores simulados
        yield mock_gen
```

---

## 📊 Métricas y Observabilidad

### Endpoints de Métricas

- **`GET /rag/metrics/prometheus`**: Métricas en formato Prometheus (jobs totales, completados, fallidos, etc.)
- **`GET /rag/metrics/snapshot/db`**: Snapshot de métricas desde DB (latencia, cobertura, costos OCR)
- **`GET /rag/metrics/snapshot/memory`**: Snapshot de estado en memoria (jobs activos, cola, etc.)

### Métricas Clave

- **Jobs totales**: Número de jobs creados por proyecto/usuario
- **Jobs completados**: Jobs que llegaron a fase `ready` exitosamente
- **Jobs fallidos**: Jobs marcados como `failed`
- **Latencia del pipeline**: Tiempo promedio por fase (convert, ocr, chunk, embed)
- **Embeddings generados**: Total de vectores activos en el índice
- **Costos de OCR**: Créditos consumidos por OCR por día/proyecto

### Logging Estructurado

Cada fase del pipeline registra logs con:
- `job_id`: Identificador del job
- `file_id`: Identificador del documento
- `phase`: Fase actual del pipeline (`convert`, `ocr`, `chunk`, `embed`, etc.)
- `message`: Descripción del evento
- `progress_pct`: Porcentaje de progreso

**Ejemplo de log**:
```
[INFO] [job_id=abc-123] [file_id=def-456] [phase=embed] Generating embeddings for 45 chunks
```

---

## 🔍 Diagnósticos SQL

El módulo incluye vistas SQL de diagnóstico en `database/rag/09_diagnostics/`:

- **`v_rag_integrity`**: Validación de integridad (chunks sin embeddings, embeddings huérfanos)
- **`v_embedding_coverage`**: Cobertura de embeddings por documento/proyecto
- **`v_pipeline_latency`**: Tiempos de ejecución por fase
- **`v_ocr_costs_daily`**: Costos de OCR agregados por día

**Uso**: Consultar estas vistas para monitorear salud del sistema y detectar anomalías.

---

## 🚀 Próximos Pasos y Extensibilidad

### Búsqueda Semántica (FASE 6)

El módulo está preparado para implementar endpoints de búsqueda semántica:

- **`POST /rag/search`**: Buscar documentos similares usando embeddings
- **`POST /rag/projects/{project_id}/semantic-search`**: Búsqueda acotada a un proyecto

**Stub existente**: La ruta está definida pero devuelve respuesta simulada. Implementación pendiente requiere:
1. Función de similitud vectorial (cosine similarity)
2. Índice vectorial optimizado (ej. HNSW con pgvector)
3. Ranking y filtrado de resultados

### Reindexación y Versionado

- **Reindexación selectiva**: Endpoint `/rag/projects/{project_id}/jobs/reindex` permite reindexar documentos específicos
- **Versionado de embeddings**: Campo `embedding_model` en `DocumentEmbedding` permite coexistencia de múltiples versiones

---

## 📚 Referencias Adicionales

- **Guía de integración con Files**: Ver `backend/app/modules/files/README.md`
- **Guía de integración con Payments**: Ver `backend/app/modules/payments/README.md`
- **Documentación de SQL**: Ver `database/rag/README.md` (si existe)
- **Tests E2E**: Ver `backend/tests/integration/test_rag_e2e_pipeline.py` como ejemplo de flujo completo

---

## 👥 Autores y Contribuidores

**Módulo RAG v2**:
- Arquitectura y diseño: DoxAI Team
- Implementación: Ixchel Beristain Mendoza
- Refactorización v2: 2025-11-28

**Contacto**: Para preguntas o contribuciones, consultar la documentación principal de DoxAI.

---

**Última actualización**: 2025-11-28 (FASE 5 - End-to-End + Observabilidad)
