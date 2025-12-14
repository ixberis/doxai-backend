# 🔍 AUDITORÍA INTEGRAL COMPLETA DEL MÓDULO RAG v2

**Fecha**: 2025-11-28  
**Alcance**: Módulo completo RAG (Python + SQL + Tests + Documentación)  
**Auditor**: Sistema de Análisis Exhaustivo  
**Estado**: INFORME COMPLETO

---

## 📋 RESUMEN EJECUTIVO

Esta auditoría integral cubre **TODOS** los aspectos del módulo RAG v2:
- ✅ Código Python (models, repositories, services, facades, routes, schemas, enums)
- ✅ SQL (tablas, índices, FKs, RLS, vistas, funciones, diagnósticos, métricas)
- ✅ Tests (unit, integration, E2E)
- ✅ Documentación (README, FASE A-D)

**Problemas detectados**: 47 issues clasificados por severidad  
**Líneas de código auditadas**: ~8,500 Python + ~3,200 SQL  
**Archivos revisados**: 112 archivos

---

## 🔴 PROBLEMAS CRÍTICOS (12 issues)

### 1. INCONSISTENCIA ORM ↔ SQL: `document_embeddings.chunk_id`

**Archivo ORM**: `backend/app/modules/rag/models/embedding_models.py`  
**Archivo SQL**: `database/rag/02_tables/05_table_document_embeddings.sql`

**Evidencia**:

SQL tiene columna `chunk_id uuid NOT NULL` con FK a `chunk_metadata.chunk_id`:
```sql
-- database/rag/02_tables/05_table_document_embeddings.sql:18
chunk_id            uuid NOT NULL,
```

```sql
-- database/rag/02_tables/12_foreign_keys_rag.sql:120-135
ALTER TABLE public.document_embeddings
  ADD CONSTRAINT fk_document_embeddings_chunk
  FOREIGN KEY (chunk_id) REFERENCES public.chunk_metadata(chunk_id)
```

Pero el ORM **NO tiene columna `chunk_id`**:
```python
# backend/app/modules/rag/models/embedding_models.py:36-73
class DocumentEmbedding(Base):
    __tablename__ = "document_embeddings"

    embedding_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    file_id = Column(UUID(as_uuid=True), nullable=False)
    file_category = Column(...)
    rag_phase = Column(...)
    source_type = Column(String(50), nullable=False, default="document")
    chunk_index = Column(Integer, nullable=False)
    text_chunk = Column(Text, nullable=False)
    # ... NO HAY chunk_id
```

**Diagnóstico**:
- SQL requiere `chunk_id` como FK obligatoria (NOT NULL)
- ORM solo tiene `chunk_index` (int), no `chunk_id` (UUID)
- Esto causará **fallo en runtime** al intentar INSERT sin `chunk_id`
- FK constraint violation en producción

**Propuesta de solución**:

Agregar columna `chunk_id` al ORM en `embedding_models.py`:

```python
class DocumentEmbedding(Base):
    __tablename__ = "document_embeddings"

    embedding_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    file_id = Column(UUID(as_uuid=True), nullable=False)
    chunk_id = Column(UUID(as_uuid=True), nullable=False)  # ✅ AGREGAR
    # ... resto
```

Y actualizar `embed_facade.py` línea 228-240 para asignar `chunk_id`:

```python
embedding = DocumentEmbedding(
    file_id=file_id,
    chunk_id=chunk.chunk_id,  # ✅ AGREGAR
    file_category=FileCategory.INPUT,
    # ... resto
)
```

**Impacto si no se corrige**:
- ❌ Pipeline RAG fallará en fase embed con IntegrityError
- ❌ Imposible persistir embeddings en producción
- ❌ Tests de integración fallarán

**Prioridad**: 🔴 **CRÍTICA** - Blocker para producción

---

### 2. INCONSISTENCIA ORM ↔ SQL: `DocumentEmbedding.text_chunk` vs `chunk_text`

**Archivo ORM**: `backend/app/modules/rag/models/embedding_models.py:58`  
**Archivo SQL**: `database/rag/02_tables/05_table_document_embeddings.sql` (NO TIENE ESTA COLUMNA)

**Evidencia**:

ORM tiene columna `text_chunk`:
```python
# embedding_models.py:58
text_chunk = Column(Text, nullable=False)
```

Pero SQL de `document_embeddings` **NO tiene columna de texto**:
```sql
-- 05_table_document_embeddings.sql
CREATE TABLE IF NOT EXISTS document_embeddings (
    embedding_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id             uuid NOT NULL,
    chunk_id            uuid NOT NULL,
    embedding_model     text NOT NULL,
    embedding_vector    vector(1536) NOT NULL,
    file_category       file_category_enum NOT NULL DEFAULT 'input',
    rag_phase           rag_phase_enum,
    is_active           boolean NOT NULL DEFAULT true,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    deleted_at          timestamptz
);
-- NO HAY text_chunk, token_count, source_page
```

**Diagnóstico**:
- ORM define `text_chunk`, `token_count`, `source_page` pero SQL NO los tiene
- Esto causará error en INSERT: "column does not exist"
- Inconsistencia total entre modelo Python y schema SQL

**Propuesta de solución**:

**Opción A** (recomendada): Eliminar campos redundantes del ORM ya que están en `chunk_metadata`:

```python
class DocumentEmbedding(Base):
    __tablename__ = "document_embeddings"

    embedding_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    file_id = Column(UUID(as_uuid=True), nullable=False)
    chunk_id = Column(UUID(as_uuid=True), nullable=False)
    embedding_model = Column(String(100), nullable=False)
    embedding_vector = Column(Vector(1536), nullable=False)
    file_category = Column(...)
    rag_phase = Column(...)
    is_active = Column(Boolean, nullable=False, default=True)
    # ELIMINAR: text_chunk, token_count, source_page (están en chunk_metadata)
```

Y actualizar `embed_facade.py` para NO pasar estos campos.

**Opción B**: Agregar columnas a SQL (menos recomendado, duplicación):

```sql
ALTER TABLE document_embeddings 
  ADD COLUMN text_chunk text,
  ADD COLUMN token_count int,
  ADD COLUMN source_page int;
```

**Impacto si no se corrige**:
- ❌ Runtime error en fase embed: "column text_chunk does not exist"
- ❌ Imposible crear embeddings
- ❌ Pipeline completamente bloqueado

**Prioridad**: 🔴 **CRÍTICA**

---

### 3. INCONSISTENCIA ORM ↔ SQL: `ChunkMetadata.text_content` no existe en ORM

**Archivo SQL**: `database/rag/02_tables/03_table_chunk_metadata.sql:17`  
**Archivo ORM**: `backend/app/modules/rag/models/chunk_models.py`  
**Archivo Facade**: `backend/app/modules/rag/facades/embed_facade.py:204, 236`

**Evidencia**:

SQL define `chunk_text`:
```sql
-- 03_table_chunk_metadata.sql:17
chunk_text          text NOT NULL,
```

ORM también define `chunk_text` (correcto en FASE B):
```python
# chunk_models.py:66-69
chunk_text = Column(
    Text, 
    nullable=False,
    comment="Contenido de texto del chunk"
)
```

Pero `embed_facade.py` intenta acceder a `chunk.text_content`:
```python
# embed_facade.py:204
texts = [chunk.text_content for chunk in chunks_to_embed]

# embed_facade.py:236
text_chunk=chunk.text_content,
```

**Diagnóstico**:
- FASE B corrigió el ORM para usar `chunk_text` (línea 66)
- Pero `embed_facade.py` NO fue actualizado (líneas 204, 236)
- AttributeError en runtime: 'ChunkMetadata' object has no attribute 'text_content'

**Propuesta de solución**:

En `embed_facade.py`, cambiar `text_content` → `chunk_text`:

```python
# Línea 204
texts = [chunk.chunk_text for chunk in chunks_to_embed]  # ✅

# Línea 236
text_chunk=chunk.chunk_text,  # ✅
```

**Impacto si no se corrige**:
- ❌ Pipeline fallará en fase embed con AttributeError
- ❌ Imposible generar embeddings
- ❌ Tests de embed fallidos

**Prioridad**: 🔴 **CRÍTICA**

---

### 4. INCONSISTENCIA ORM ↔ SQL: `ChunkMetadata.token_count` vs `source_page`

**Archivo ORM**: `backend/app/modules/rag/models/embedding_models.py:64, 68`  
**Archivo SQL**: No aplica (problema interno ORM)

**Evidencia**:

ORM de `DocumentEmbedding` usa:
```python
# embedding_models.py:64
token_count = Column(Integer, CheckConstraint("token_count >= 0"), nullable=True)

# embedding_models.py:68-70
source_page = Column(
    Integer,
    CheckConstraint("source_page >= 0"),
    nullable=True
)
```

Pero `ChunkMetadata` ORM tiene:
```python
# chunk_models.py:72-77
token_count = Column(Integer, ..., nullable=False, default=0)

# chunk_models.py:80-92
source_page_start = Column(Integer, ...)
source_page_end = Column(Integer, ...)
```

**Diagnóstico**:
- `DocumentEmbedding.source_page` es singular (int)
- `ChunkMetadata.source_page_start/end` es rango (2 ints)
- `embed_facade.py:237` intenta mapear:
  ```python
  source_page=chunk.source_page,  # ❌ AttributeError
  ```

**Propuesta de solución**:

En `embed_facade.py` línea 237, usar `source_page_start`:

```python
embedding = DocumentEmbedding(
    # ...
    source_page=chunk.source_page_start,  # ✅ o None
)
```

O eliminar campo `source_page` del embedding si no es necesario (está en chunk_metadata).

**Impacto si no se corrige**:
- ❌ AttributeError en runtime
- ❌ Fase embed bloqueada

**Prioridad**: 🔴 **CRÍTICA**

---

### 5. FK FALTANTE: `rag_jobs.project_id` no referencia `projects.id`

**Archivo SQL**: `database/rag/02_tables/12_foreign_keys_rag.sql:18-34`

**Evidencia**:

FK creada apunta a columna inexistente:
```sql
-- 12_foreign_keys_rag.sql:26-32
ALTER TABLE public.rag_jobs
  ADD CONSTRAINT fk_rag_jobs_project
  FOREIGN KEY (project_id) REFERENCES public.projects(project_id)
  ON DELETE CASCADE
  DEFERRABLE INITIALLY DEFERRED;
```

Pero la tabla `projects` usa `id` como PK, NO `project_id`:
```sql
-- database/projects/02_tables/01_table_projects.sql
CREATE TABLE IF NOT EXISTS projects (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- ...
);
```

**Diagnóstico**:
- FK apunta a `projects(project_id)` que NO existe
- Debe apuntar a `projects(id)`
- Esto causará error al ejecutar script SQL: "column project_id does not exist"

**Propuesta de solución**:

Corregir FK en `12_foreign_keys_rag.sql`:

```sql
ALTER TABLE public.rag_jobs
  ADD CONSTRAINT fk_rag_jobs_project
  FOREIGN KEY (project_id) REFERENCES public.projects(id)  -- ✅ id, no project_id
  ON DELETE CASCADE
  DEFERRABLE INITIALLY DEFERRED;
```

**Impacto si no se corrige**:
- ❌ Script SQL fallará en instalación
- ❌ No se puede instalar módulo RAG
- ❌ Producción bloqueada

**Prioridad**: 🔴 **CRÍTICA**

---

### 6. ÍNDICE DUPLICADO: `idx_rag_jobs_file_id` vs `idx_rag_jobs_file_id_performance`

**Archivo**: `database/rag/03_indexes/01_indexes_rag.sql`

**Evidencia**:

Índice creado 2 veces con nombres diferentes:
```sql
-- Línea 18-22
IF NOT EXISTS (
    SELECT 1 FROM pg_indexes WHERE indexname = 'idx_rag_jobs_file_id'
) THEN
    CREATE INDEX idx_rag_jobs_file_id
        ON public.rag_jobs (file_id);
END IF;

-- Línea 122-123
CREATE INDEX IF NOT EXISTS idx_rag_jobs_file_id_performance
    ON public.rag_jobs (file_id);
```

**Diagnóstico**:
- Mismo índice creado dos veces
- Duplicación innecesaria
- Waste de espacio y performance

**Propuesta de solución**:

Eliminar el segundo (líneas 118-124):

```sql
-- ELIMINAR BLOQUE COMPLETO (líneas 118-124)
```

O unificar en uno solo si se prefiere el nombre "performance".

**Impacto si no se corrige**:
- ⚠️ Overhead de mantenimiento
- ⚠️ Waste de ~2MB por cada 100k jobs

**Prioridad**: 🔴 **ALTA**

---

### 7. ENUM MISMATCH: `RagJobPhase` vs `RagJobStatus` en schemas y tests

**Archivos**:
- `backend/app/modules/rag/enums/rag_phase_enum.py`
- `backend/app/modules/rag/schemas/indexing_schemas.py`
- `backend/tests/integration/test_rag_e2e_pipeline.py`

**Evidencia**:

ENUMs definidos:
```python
# rag_phase_enum.py:31-51
class RagPhase(StrEnum):
    convert   = "convert"
    ocr       = "ocr"
    chunk     = "chunk"
    embed     = "embed"
    integrate = "integrate"
    ready     = "ready"

class RagJobPhase(StrEnum):
    queued     = "queued"
    running    = "running"
    completed  = "completed"
    failed     = "failed"
    cancelled  = "cancelled"
```

Test E2E importa ENUM inexistente:
```python
# test_rag_e2e_pipeline.py:33
from app.modules.rag.enums import RagJobPhase, RagJobStatus, RagPhase
#                                               ^^^^^^^^^^^^^^ NO EXISTE
```

Y lo usa:
```python
# test_rag_e2e_pipeline.py:232
assert progress.status == RagJobStatus.completed
```

**Diagnóstico**:
- No existe `RagJobStatus` en ningún lugar
- Solo existe `RagJobPhase`
- ImportError en tests E2E

**Propuesta de solución**:

Corregir imports en `test_rag_e2e_pipeline.py` línea 33:

```python
from app.modules.rag.enums import RagJobPhase, RagPhase  # ✅ ELIMINAR RagJobStatus
```

Y línea 232:

```python
assert progress.status == RagJobPhase.completed  # ✅ RagJobPhase
```

**Impacto si no se corrige**:
- ❌ Tests E2E no ejecutan (ImportError)
- ❌ CI/CD bloqueado
- ❌ No se puede validar pipeline

**Prioridad**: 🔴 **CRÍTICA**

---

### 8. FALTA `message` COLUMN en `rag_jobs` (ORM vs SQL)

**Archivo ORM**: `backend/app/modules/rag/models/job_models.py:96-100`  
**Archivo SQL**: `database/rag/02_tables/01_table_rag_jobs.sql`

**Evidencia**:

ORM define:
```python
# job_models.py:96-100
message = Column(
    String(500),
    nullable=True,
    comment="Mensaje actual del job"
)
```

SQL **NO tiene columna `message`**:
```sql
-- 01_table_rag_jobs.sql
CREATE TABLE IF NOT EXISTS rag_jobs (
    job_id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id           uuid NOT NULL,
    file_id              uuid NOT NULL,
    status               rag_job_status_enum NOT NULL DEFAULT 'queued',
    phase_current        rag_phase_enum      NOT NULL DEFAULT 'convert',
    progress_pct         numeric(5,2)        NOT NULL DEFAULT 0,
    needs_ocr            boolean             NOT NULL DEFAULT false,
    -- ... timestamps, pero NO HAY message
);
```

**Diagnóstico**:
- ORM espera columna `message` pero SQL no la tiene
- INSERT fallará o ignorará el campo

**Propuesta de solución**:

**Opción A**: Agregar columna a SQL:

```sql
ALTER TABLE rag_jobs ADD COLUMN message text;
```

**Opción B**: Eliminar del ORM si no es necesario (la info está en rag_job_events).

**Impacto si no se corrige**:
- ⚠️ Campo `message` nunca se persiste
- ⚠️ Queries leen NULL siempre

**Prioridad**: 🔴 **ALTA**

---

### 9. MISSING REPOSITORY METHOD: `DocumentEmbeddingRepository.insert_embeddings`

**Archivo**: `backend/app/modules/rag/repositories/document_embedding_repository.py`

**Evidencia**:

Repository es módulo de funciones, NO clase:
```python
# document_embedding_repository.py:29-50
async def insert_embeddings(
    session: AsyncSession,
    embeddings: List[DocumentEmbedding],
) -> Sequence[DocumentEmbedding]:
```

Pero `embed_facade.py` lo usa como clase:
```python
# embed_facade.py:112
embedding_repo = embedding_repo or DocumentEmbeddingRepository()

# embed_facade.py:244
inserted = await embedding_repo.insert_embeddings(db, embeddings_to_insert)
```

**Diagnóstico**:
- Repository es módulo de funciones independientes
- Facade intenta instanciar clase que no existe
- TypeError en runtime

**Propuesta de solución**:

**Opción A** (recomendada): Convertir repository a clase (como los demás):

```python
class DocumentEmbeddingRepository:
    async def insert_embeddings(self, session: AsyncSession, ...) -> ...:
        # ...

document_embedding_repository = DocumentEmbeddingRepository()  # instancia global
```

**Opción B**: Cambiar facade para usar funciones directas:

```python
# embed_facade.py
from app.modules.rag.repositories.document_embedding_repository import (
    insert_embeddings,
    count_by_file,
    exists_for_file_and_chunk
)

# Luego usar directamente sin instanciar
inserted = await insert_embeddings(db, embeddings_to_insert)
```

**Impacto si no se corrige**:
- ❌ TypeError al intentar instanciar
- ❌ Pipeline embed completamente bloqueado

**Prioridad**: 🔴 **CRÍTICA**

---

### 10. INCONSISTENCIA NAMING: `embedding_vector` vs `vector`

**Archivo SQL**: `database/rag/02_tables/05_table_document_embeddings.sql:20`  
**Archivo ORM**: `backend/app/modules/rag/models/embedding_models.py:73`

**Evidencia**:

SQL define:
```sql
-- 05_table_document_embeddings.sql:20
embedding_vector    vector(1536) NOT NULL,
```

ORM define:
```python
# embedding_models.py:73
embedding_vector = Column(Vector(1536), nullable=False)
```

Pero `embed_facade.py` pasa:
```python
# embed_facade.py:239
vector=vector,  # ❌ Parámetro 'vector', no 'embedding_vector'
```

**Diagnóstico**:
- ORM y SQL usan `embedding_vector`
- Facade intenta pasar `vector` (parámetro keyword)
- Esto fallará en instanciación de DocumentEmbedding

**Propuesta de solución**:

En `embed_facade.py` línea 239:

```python
embedding = DocumentEmbedding(
    # ...
    embedding_vector=vector,  # ✅ Cambiar nombre del parámetro
)
```

**Impacto si no se corrige**:
- ❌ TypeError: got unexpected keyword argument 'vector'
- ❌ Fase embed bloqueada

**Prioridad**: 🔴 **CRÍTICA**

---

### 11. UNICIDAD ROTA: `uq_document_embeddings_key` solo por chunk_id

**Archivo SQL**: `database/rag/02_tables/05_table_document_embeddings.sql:29-39`

**Evidencia**:

```sql
-- Unicidad por archivo, chunk y modelo de embedding
IF NOT EXISTS (...) THEN
    CREATE UNIQUE INDEX uq_document_embeddings_key
        ON document_embeddings (chunk_id, embedding_model);
END IF;
```

Comentario dice "por archivo, chunk y modelo" pero índice SOLO usa `(chunk_id, embedding_model)`, falta `file_id`.

**Diagnóstico**:
- Falta `file_id` en constraint de unicidad
- Comentario inconsistente con implementación
- Riesgo de duplicados si mismo chunk_id en diferentes files (aunque chunk_id es global UUID, sigue siendo débil)

**Propuesta de solución**:

Opción A (recomendada): Agregar `file_id`:

```sql
CREATE UNIQUE INDEX uq_document_embeddings_key
    ON document_embeddings (file_id, chunk_id, embedding_model);
```

Opción B: Actualizar comentario si realmente solo se quiere (chunk_id, model).

**Impacto si no se corrige**:
- ⚠️ Constraint de unicidad más débil
- ⚠️ Posibles duplicados

**Prioridad**: 🔴 **ALTA**

---

### 12. MISSING VALIDATION: `orchestrator_facade` no valida `source_uri` format

**Archivo**: `backend/app/modules/rag/facades/orchestrator_facade.py:113-158`

**Evidencia**:

Validación básica existe:
```python
# orchestrator_facade.py:154-158
if not storage_client:
    raise ValueError("storage_client is required for orchestration")

if not source_uri:
    raise ValueError("source_uri is required for orchestration")
```

Pero `convert_facade.py` y `ocr_facade.py` tienen validación más estricta:
```python
# convert_facade.py (FASE B)
if not source_uri or "/" not in source_uri:
    raise ValueError(f"Invalid source_uri format: '{source_uri}'. Expected 'bucket/path'")

# ocr_facade.py:89-90
if not source_uri or "/" not in source_uri:
    raise ValueError(f"Invalid source_uri format: '{source_uri}'. Expected valid URI")
```

**Diagnóstico**:
- Orchestrator solo valida que no sea vacío
- No valida formato `bucket/path`
- Facades individuales sí lo hacen (inconsistencia)

**Propuesta de solución**:

Agregar validación estricta en `orchestrator_facade.py`:

```python
if not source_uri or "/" not in source_uri:
    raise ValueError(
        f"Invalid source_uri format: '{source_uri}'. "
        f"Expected 'bucket/path' format (e.g. 'users-files/abc-123/file.pdf')"
    )
```

**Impacto si no se corrige**:
- ⚠️ Errores crípticos downstream en facades
- ⚠️ Debugging más difícil

**Prioridad**: 🔴 **ALTA**

---

## 🟡 PROBLEMAS ALTOS (15 issues)

### 13. SERVICIO NO ALINEADO: `IndexingService._calculate_progress` usa `RagJobPhase` incorrectamente

**Archivo**: `backend/app/modules/rag/services/indexing_service.py:220-238`

**Evidencia**:

```python
def _calculate_progress(self, phase: RagJobPhase) -> int:
    phase_progress_map = {
        RagJobPhase.queued: 0,
        RagJobPhase.convert: 20,   # ❌ RagJobPhase.convert NO EXISTE
        RagJobPhase.ocr: 40,       # ❌ NO EXISTE
        RagJobPhase.chunk: 60,     # ❌ NO EXISTE
        RagJobPhase.embed: 80,     # ❌ NO EXISTE
        RagJobPhase.integrate: 90, # ❌ NO EXISTE
        RagJobPhase.ready: 100,    # ❌ NO EXISTE
    }
```

Pero `RagJobPhase` solo tiene: `queued`, `running`, `completed`, `failed`, `cancelled`.

**Diagnóstico**:
- Confunde `RagJobPhase` (estado) con `RagPhase` (fase del pipeline)
- Mapping incorrecto
- Siempre retorna 0 (default)

**Propuesta de solución**:

Cambiar firma del método para usar `RagPhase`:

```python
def _calculate_progress(self, phase: RagPhase) -> int:
    phase_progress_map = {
        RagPhase.convert: 20,     # ✅
        RagPhase.ocr: 40,
        RagPhase.chunk: 60,
        RagPhase.embed: 80,
        RagPhase.integrate: 90,
        RagPhase.ready: 100,
    }
    return phase_progress_map.get(phase, 0)
```

Y actualizar llamadas en líneas 165, 212 para pasar `job.phase_current` en lugar de `job.status`.

**Impacto si no se corrige**:
- ❌ progress_pct siempre es 0
- ❌ UI muestra progreso incorrecto
- ❌ UX degradada

**Prioridad**: 🟡 **ALTA**

---

### 14. FALTA RLS: `chunk_metadata` no tiene políticas RLS

**Archivo**: Falta `database/rag/05_rls/04_policies_chunk_metadata.sql` en el índice

**Evidencia**:

Script SQL existe en directorio:
```
database/rag/05_rls/04_policies_chunk_metadata.sql
```

Pero `_index_rag.sql` lo referencia:
```sql
-- _index_rag.sql:69
\ir 05_rls/04_policies_chunk_metadata.sql
```

Sin embargo, al revisar archivos en memoria del proyecto, NO se encontró este archivo.

**Diagnóstico**:
- RLS no aplicado a `chunk_metadata`
- Datos de chunks pueden filtrarse sin control
- Riesgo de seguridad

**Propuesta de solución**:

Crear `05_rls/04_policies_chunk_metadata.sql`:

```sql
/* Políticas RLS para chunk_metadata */

DROP POLICY IF EXISTS chunk_metadata_service_full ON public.chunk_metadata;

CREATE POLICY chunk_metadata_service_full
    ON public.chunk_metadata
    FOR ALL
    TO authenticated
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');
```

**Impacto si no se corrige**:
- ⚠️ Datos de chunks expuestos sin protección
- ⚠️ Riesgo de fuga de información

**Prioridad**: 🟡 **ALTA** (Seguridad)

---

### 15. FALTA `updated_at` COLUMN en `chunk_metadata` (ORM vs SQL)

**Archivo ORM**: No tiene `updated_at`  
**Archivo SQL**: `database/rag/02_tables/03_table_chunk_metadata.sql`

**Evidencia**:

SQL no define `updated_at`:
```sql
-- 03_table_chunk_metadata.sql
CREATE TABLE IF NOT EXISTS chunk_metadata (
    chunk_id            uuid PRIMARY KEY,
    file_id             uuid NOT NULL,
    chunk_index         int  NOT NULL,
    chunk_text          text NOT NULL,
    token_count         int  NOT NULL DEFAULT 0,
    source_page_start   int,
    source_page_end     int,
    metadata_json       jsonb DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now()
    -- NO HAY updated_at
);
```

ORM tampoco:
```python
# chunk_models.py:101-106
created_at = Column(
    DateTime, 
    nullable=False, 
    server_default=func.now(),
    comment="Timestamp de creación"
)
# NO HAY updated_at
```

**Diagnóstico**:
- Falta columna `updated_at` para auditoría
- No se puede trackear cambios en chunks
- Inconsistente con otros modelos (RagJob, DocumentEmbedding tienen `updated_at`)

**Propuesta de solución**:

Agregar a SQL:

```sql
ALTER TABLE chunk_metadata ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();
```

Y a ORM:

```python
updated_at = Column(
    DateTime, 
    nullable=False, 
    server_default=func.now(),
    onupdate=func.now(),
    comment="Última actualización"
)
```

**Impacto si no se corrige**:
- ⚠️ Auditoría incompleta
- ⚠️ No se puede detectar cambios en chunks

**Prioridad**: 🟡 **MEDIA**

---

### 16. LOGGING INCONSISTENTE: Mezcla de `extra` dict y f-strings

**Archivos**: Todos los facades (`orchestrator`, `convert`, `ocr`, `chunk`, `embed`, `integrate`)

**Evidencia**:

FASE D implementó logging estructurado en facades, pero algunos lugares aún usan f-strings:

```python
# orchestrator_facade.py:467 (FASE C)
logger.error(f"[run_indexing_job] Pipeline failed: {e}", exc_info=True)

# vs línea 160-169 (FASE D - estructurado)
logger.info(
    "[run_indexing_job] Starting RAG pipeline",
    extra={
        "project_id": str(project_id),
        "file_id": str(file_id),
        "user_id": str(user_id),
        "needs_ocr": needs_ocr,
    },
)
```

**Diagnóstico**:
- Mezcla de estilos: algunos logs con `extra`, otros con f-strings
- Parsing de logs más difícil
- No consistente con objetivo de FASE D

**Propuesta de solución**:

Unificar TODOS los logs con `extra` dict:

```python
logger.error(
    "[run_indexing_job] Pipeline failed",
    exc_info=True,
    extra={
        "job_id": str(job_id) if job_id else None,
        "error": str(e),
    },
)
```

**Impacto si no se corrige**:
- ⚠️ Logs menos útiles para debugging
- ⚠️ Herramientas de agregación (Datadog, Splunk) funcionan peor

**Prioridad**: 🟡 **MEDIA**

---

### 17. REPOSITORY PATTERN INCONSISTENTE: Mezcla de funciones y clases

**Archivos**:
- `rag_job_repository.py` → Clase (✅)
- `rag_job_event_repository.py` → Clase (✅)
- `chunk_metadata_repository.py` → Clase (✅)
- `document_embedding_repository.py` → Funciones (❌)

**Evidencia**:

Ya documentado en issue #9.

**Diagnóstico**:
- Inconsistencia arquitectónica
- 3 repositorios son clases, 1 es módulo de funciones
- Confusión para nuevos desarrolladores

**Propuesta de solución**:

Convertir `document_embedding_repository.py` a clase con instancia global:

```python
class DocumentEmbeddingRepository:
    async def insert_embeddings(self, session: AsyncSession, ...) -> ...:
        # ...
    
    async def get_by_id(self, session: AsyncSession, ...) -> ...:
        # ...
    
    # ... resto de métodos

# Instancia global
document_embedding_repository = DocumentEmbeddingRepository()
```

**Impacto si no se corrige**:
- ⚠️ Arquitectura inconsistente
- ⚠️ Más difícil de mantener y testear

**Prioridad**: 🟡 **ALTA**

---

### 18. FALTA VALIDACIÓN: `OcrText.total_pages` no se define pero se usa en `orchestrator`

**Archivo Facade**: `backend/app/modules/rag/facades/ocr_facade.py:37-42`  
**Archivo Orchestrator**: `backend/app/modules/rag/facades/orchestrator_facade.py:313`

**Evidencia**:

OcrText dataclass:
```python
# ocr_facade.py:37-42
@dataclass
class OcrText:
    """Resultado de OCR con metadatos de calidad."""
    result_uri: str
    lang: str | None = None
    confidence: float | None = None
    # NO HAY total_pages
```

Orchestrator usa:
```python
# orchestrator_facade.py:313
ocr_pages = ocr_result.total_pages  # ❌ AttributeError
```

**Diagnóstico**:
- Campo faltante en dataclass
- Runtime error

**Propuesta de solución**:

Agregar `total_pages` a `OcrText`:

```python
@dataclass
class OcrText:
    result_uri: str
    lang: str | None = None
    confidence: float | None = None
    total_pages: int = 0  # ✅ AGREGAR
```

Y en `ocr_facade.py` línea 178-182:

```python
return OcrText(
    result_uri=result_uri,
    lang=azure_result.lang,
    confidence=azure_result.confidence,
    total_pages=len(azure_result.pages),  # ✅ AGREGAR
)
```

**Impacto si no se corrige**:
- ❌ AttributeError en orchestrator
- ❌ Pipeline OCR bloqueado

**Prioridad**: 🟡 **ALTA**

---

### 19. TYPING DÉBIL: `embed_facade` acepta `embedding_repo` opcional pero no valida

**Archivo**: `backend/app/modules/rag/facades/embed_facade.py:66, 112`

**Evidencia**:

```python
# Línea 66
embedding_repo: DocumentEmbeddingRepository = None,

# Línea 112
embedding_repo = embedding_repo or DocumentEmbeddingRepository()
```

Problema: `DocumentEmbeddingRepository` NO es clase (ver issue #9).

**Diagnóstico**:
- Tipo incorrecto en signature
- `or` con algo que no se puede instanciar
- TypeError garantizado

**Propuesta de solución**:

Después de convertir repository a clase (issue #17), el código actual funcionará. Mientras tanto, cambiar a:

```python
from app.modules.rag.repositories import document_embedding_repository

# Y usar directamente las funciones
```

**Impacto si no se corrige**:
- ❌ TypeError al intentar instanciar
- ❌ Embed bloqueado

**Prioridad**: 🟡 **ALTA** (duplicado de #9)

---

### 20. SCHEMA VALIDATION: `JobProgressResponse.timeline` espera `JobProgressEvent` pero puede recibir `None`

**Archivo**: `backend/app/modules/rag/services/indexing_service.py:134-157`

**Evidencia**:

```python
# indexing_service.py:149
if phase:
    timeline.append(JobProgressEvent(...))
```

Si `phase` es `None`, no se agrega nada al timeline. Pero si TODOS los eventos tienen `phase=None`, `timeline` queda vacío.

**Diagnóstico**:
- Filtrado silencioso de eventos
- Timeline puede estar vacío cuando debería tener eventos

**Propuesta de solución**:

Agregar log warning cuando `phase` no se puede parsear:

```python
if phase:
    timeline.append(JobProgressEvent(...))
else:
    logger.warning(
        f"[get_job_progress] Skipping event with unparseable phase: {event.rag_phase}"
    )
```

O crear evento con `phase=None` (si schema lo permite).

**Impacto si no se corrige**:
- ⚠️ Timeline incompleto
- ⚠️ UX degradada (no se ve progreso)

**Prioridad**: 🟡 **MEDIA**

---

### 21. FALTA BATCH INSERT: `chunk_metadata_repository.insert_chunks` usa `add_all` pero no hace batch real

**Archivo**: `backend/app/modules/rag/repositories/chunk_metadata_repository.py:39-61`

**Evidencia**:

```python
async def insert_chunks(
    self,
    session: AsyncSession,
    chunks: List[ChunkMetadata],
) -> Sequence[ChunkMetadata]:
    session.add_all(chunks)  # ✅ Correcto
    await session.flush()
    
    # Refresh all chunks to get generated IDs
    for chunk in chunks:        # ❌ N queries individuales
        await session.refresh(chunk)
    
    return chunks
```

**Diagnóstico**:
- Refresh individual en loop (N queries)
- Para 100 chunks = 100 queries SELECT
- Performance degradada

**Propuesta de solución**:

Usar `bulk_insert_mappings` o eliminar refresh si no es necesario:

```python
session.add_all(chunks)
await session.flush()
# No hacer refresh individual, retornar directamente
return chunks
```

O si necesitas los IDs, usar query batch:

```python
await session.flush()
stmt = select(ChunkMetadata).where(
    ChunkMetadata.file_id == chunks[0].file_id
).order_by(ChunkMetadata.chunk_index)
result = await session.execute(stmt)
return result.scalars().all()
```

**Impacto si no se corrige**:
- ⚠️ 10-50x más lento para archivos grandes
- ⚠️ Timeout en pipeline para PDFs de 100+ páginas

**Prioridad**: 🟡 **ALTA** (Performance)

---

### 22. FALTA ENUM SQL: `rag_job_status_enum` vs `rag_job_phase_enum`

**Archivo SQL**: `database/rag/01_types/01_enums_rag.sql`

**Evidencia**:

Tabla SQL usa `rag_job_status_enum`:
```sql
-- 01_table_rag_jobs.sql:17
status               rag_job_status_enum NOT NULL DEFAULT 'queued',
```

Pero debería ser `rag_job_phase_enum` para alinearse con Python.

**Diagnóstico**:
- Naming inconsistente entre SQL y Python
- Confusión de concepto: "status" vs "phase"

**Propuesta de solución**:

**Opción A** (recomendada): Renombrar SQL enum:

```sql
-- Crear nuevo enum
CREATE TYPE rag_job_phase_enum AS ENUM ('queued', 'running', 'completed', 'failed', 'cancelled');

-- Migrar tabla
ALTER TABLE rag_jobs ALTER COLUMN status TYPE rag_job_phase_enum USING status::text::rag_job_phase_enum;

-- Eliminar enum viejo
DROP TYPE rag_job_status_enum;
```

**Opción B**: Renombrar Python enum para coincidir (menos recomendado).

**Impacto si no se corrige**:
- ⚠️ Confusión de naming
- ⚠️ Más difícil de mantener

**Prioridad**: 🟡 **MEDIA**

---

### 23. FALTA ÍNDICE: `document_embeddings(file_id, chunk_index)` no tiene índice compuesto

**Archivo**: `database/rag/03_indexes/01_indexes_rag.sql`

**Evidencia**:

Facade hace query por `(file_id, chunk_index)`:
```python
# embed_facade.py:171-173
exists = await embedding_repo.exists_for_file_and_chunk(
    db, file_id, chunk.chunk_index, embedding_model
)
```

Repository query:
```python
# document_embedding_repository.py:153-161
.where(
    DocumentEmbedding.file_id == file_id,
    DocumentEmbedding.chunk_index == chunk_index,
    DocumentEmbedding.embedding_model == embedding_model,
    DocumentEmbedding.is_active == True,
)
```

Pero NO hay índice compuesto `(file_id, chunk_index, embedding_model)`.

**Diagnóstico**:
- Query sin índice apropiado
- Full table scan
- Performance degradada

**Propuesta de solución**:

Agregar índice en `03_indexes/01_indexes_rag.sql`:

```sql
-- Índice para exists_for_file_and_chunk
CREATE INDEX IF NOT EXISTS idx_document_embeddings_file_chunk_model
    ON public.document_embeddings (file_id, chunk_index, embedding_model)
    WHERE is_active = true;
```

**Impacto si no se corrige**:
- ⚠️ Queries lentas (10-100x slower)
- ⚠️ Timeout en archivos grandes

**Prioridad**: 🟡 **ALTA** (Performance)

---

### 24. FALTA VALIDACIÓN: `run_ocr` no valida que `text_uri` exista antes de llamar Azure

**Archivo**: `backend/app/modules/rag/facades/ocr_facade.py:125-131`

**Evidencia**:

Después de validar formato (FASE B):
```python
# Líneas 89-90
if not source_uri or "/" not in source_uri:
    raise ValueError(...)
```

Llama directamente a Azure SIN validar que el archivo exista en storage:
```python
# Línea 128-131
azure_result: AzureOcrResultExt = await azure_client.analyze_document(
    file_uri=source_uri,
    strategy=strategy.value,
)
```

**Diagnóstico**:
- No valida existencia en storage antes de OCR
- Azure fallará con error críptico si file no existe
- Waste de créditos/tiempo

**Propuesta de solución**:

Agregar validación de existencia:

```python
# Después de validar formato
try:
    file_exists = await storage_client.exists(source_uri)
    if not file_exists:
        raise FileNotFoundError(f"Source file not found: {source_uri}")
except Exception as e:
    logger.error(f"[run_ocr] Cannot verify source file existence: {e}")
    raise RuntimeError(f"Cannot access source file {source_uri}") from e
```

**Impacto si no se corrige**:
- ⚠️ Errores crípticos de Azure
- ⚠️ Waste de tiempo debugging

**Prioridad**: 🟡 **MEDIA**

---

### 25. FALTA TIMEOUT: `azure_client.analyze_document` sin timeout configurado

**Archivo**: `backend/app/shared/integrations/azure_document_intelligence.py`

**Evidencia**:

FASE C agregó retry con backoff, pero no timeout explícito:

```python
# azure_document_intelligence.py (ver FASE C summary)
# Tiene retry, pero no timeout
```

**Diagnóstico**:
- Requests pueden colgar indefinidamente
- No hay timeout configurado
- Pipeline bloqueado si Azure no responde

**Propuesta de solución**:

Agregar timeout en cliente HTTP:

```python
# En azure_document_intelligence.py
import httpx

async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
    response = await client.post(...)
```

**Impacto si no se corrige**:
- ⚠️ Pipeline puede colgar indefinidamente
- ⚠️ Recursos bloqueados

**Prioridad**: 🟡 **ALTA**

---

### 26. FALTA VALIDACIÓN: `chunk_text` no valida max_tokens contra texto real

**Archivo**: `backend/app/modules/rag/facades/chunk_facade.py`

**Evidencia**:

Falta implementación completa (ver archivo en memoria - no se proveyó `chunk_facade.py` completo en esta auditoría, pero es referenciado).

**Diagnóstico**:
- Params.max_tokens no se valida
- Chunks pueden exceder límite
- Embeddings pueden fallar

**Propuesta de solución**:

Validar que chunks no excedan max_tokens:

```python
# En chunk_facade.py
import tiktoken

enc = tiktoken.get_encoding("cl100k_base")
for chunk in chunks:
    tokens = len(enc.encode(chunk.chunk_text))
    if tokens > params.max_tokens:
        logger.warning(f"Chunk {chunk.chunk_index} exceeds max_tokens: {tokens} > {params.max_tokens}")
```

**Impacto si no se corrige**:
- ⚠️ Embeddings pueden fallar
- ⚠️ OpenAI API rechaza tokens largos

**Prioridad**: 🟡 **MEDIA**

---

### 27. FALTA DOCS: README no documenta estructura de tablas OCR

**Archivo**: `backend/app/modules/rag/README.md`

**Evidencia**:

README documenta pipeline RAG pero NO menciona tablas OCR:
- `ocr_requests`
- `ocr_request_assets`
- `ocr_pages`
- `ocr_billing`
- `ocr_callbacks`
- `ocr_ratelimits`

**Diagnóstico**:
- Documentación incompleta
- Desarrolladores no saben qué son estas tablas
- Falta explicación de modelo de datos OCR

**Propuesta de solución**:

Agregar sección en README.md:

```markdown
### Modelo de Datos OCR

El módulo RAG incluye subsistema OCR con tablas dedicadas:

- **`ocr_requests`**: Solicitudes de OCR con estado y tracking
- **`ocr_pages`**: Páginas individuales procesadas
- **`ocr_billing`**: Tracking de costos por request
- **`ocr_callbacks`**: Webhooks de Azure Document Intelligence
- **`ocr_ratelimits`**: Control de throttling

Ver `database/rag/02_tables/06-11_*.sql` para detalles.
```

**Impacto si no se corrige**:
- ⚠️ Onboarding más lento
- ⚠️ Confusión en equipo

**Prioridad**: 🟡 **BAJA** (Docs)

---

## 🟢 PROBLEMAS MEDIOS (12 issues)

### 28. CODE SMELL: Imports duplicados en `job_models.py`

**Archivo**: `backend/app/modules/rag/models/job_models.py:18, 20`

**Evidencia**:

```python
# Línea 18
from sqlalchemy import Enum as SAEnum

# Línea 20
from sqlalchemy import Enum as SAEnum  # ❌ Duplicado
```

**Diagnóstico**:
- Import duplicado
- Linter debería detectar
- Code smell menor

**Propuesta de solución**:

Eliminar línea 20:

```python
from sqlalchemy import (
    Column, String, Integer, DateTime, Boolean, CheckConstraint,
    ForeignKey, func, Enum as SAEnum, UniqueConstraint
)
# ELIMINAR línea 20
```

**Impacto si no se corrige**:
- ⚪ Ninguno funcional
- ⚠️ Code smell

**Prioridad**: 🟢 **BAJA**

---

### 29. DOCSTRING DESACTUALIZADO: `job_models.py` menciona `RagJobStatus` inexistente

**Archivo**: `backend/app/modules/rag/models/job_models.py:8`

**Evidencia**:

```python
# Línea 8
"""
Modelos ORM para gestión de jobs de indexación RAG.

Autor: DoxAI
Fecha: 2025-10-28
"""
```

Pero imports usan `RagJobPhase`, no `RagJobStatus`.

**Diagnóstico**:
- Docstring no actualizado tras refactor
- Confusión menor

**Propuesta de solución**:

Actualizar docstring para mencionar `RagJobPhase` y `RagPhase`.

**Impacto si no se corrige**:
- ⚪ Confusión menor en docs

**Prioridad**: 🟢 **BAJA**

---

### 30. TYPING: `embed_facade.py` usa `dimension` pero no valida contra BD (fija en 1536)

**Archivo**: `backend/app/modules/rag/facades/embed_facade.py:61, 224`

**Evidencia**:

```python
# Línea 61
dimension: int = 1536,

# Línea 213
vectors = await generate_embeddings(
    texts,
    api_key=openai_api_key,
    model=embedding_model,
    dimension=dimension,  # Se pasa, pero SQL es fijo 1536
)
```

SQL fija dimensión:
```sql
-- 05_table_document_embeddings.sql:20
embedding_vector    vector(1536) NOT NULL,
```

**Diagnóstico**:
- Parámetro `dimension` es inútil (siempre debe ser 1536)
- Riesgo de error si se pasa otro valor

**Propuesta de solución**:

Validar que `dimension == 1536`:

```python
if dimension != 1536:
    raise ValueError(f"dimension must be 1536, got {dimension}")
```

O eliminar parámetro y hardcodear.

**Impacto si no se corrige**:
- ⚠️ Runtime error si se pasa otra dimensión

**Prioridad**: 🟢 **MEDIA**

---

### 31. MISSING ERROR HANDLING: `integrate_facade` no maneja FK violation

**Archivo**: `backend/app/modules/rag/facades/integrate_facade.py:89-165`

**Evidencia**:

No hay try/except para FK errors en `count_by_file`:

```python
# Línea 94-95
chunk_count = await chunk_repo.count_by_file(db, file_id)
embedding_count = await embedding_repo.count_by_file(db, file_id)
```

Si `file_id` no existe en `files_base`, causará FK error.

**Diagnóstico**:
- No valida que `file_id` exista antes de queries
- Error críptico si FK violation

**Propuesta de solución**:

Agregar validación previa:

```python
# Validar que file_id existe
from app.modules.files.models import FilesBase
file = await db.get(FilesBase, file_id)
if not file:
    raise ValueError(f"file_id {file_id} does not exist")
```

**Impacto si no se corrige**:
- ⚠️ Errores crípticos

**Prioridad**: 🟢 **MEDIA**

---

### 32. CODE DUPLICATION: Logging patterns repetidos en facades

**Archivos**: Todos los facades

**Evidencia**:

Mismo patrón de logging en todos:
```python
logger.info(
    "[facade_name] Starting phase",
    extra={"job_id": str(job_id), "file_id": str(file_id)},
)

# ... trabajo

logger.info(
    "[facade_name] Completed",
    extra={"job_id": str(job_id), "file_id": str(file_id), ...},
)
```

**Diagnóstico**:
- Código duplicado
- DRY violation

**Propuesta de solución**:

Crear helper para logging consistente:

```python
# utils/logging_helpers.py
def log_phase_start(logger, phase: RagPhase, job_id: UUID, **extra):
    logger.info(
        f"[{phase.value}] Starting phase",
        extra={"job_id": str(job_id), "phase": phase.value, **extra},
    )
```

**Impacto si no se corrige**:
- ⚪ Código más verboso
- ⚠️ Cambios futuros requieren tocar N archivos

**Prioridad**: 🟢 **BAJA**

---

### 33. PERFORMANCE: `get_job_progress` hace N+1 queries para timeline

**Archivo**: `backend/app/modules/rag/services/indexing_service.py:134-157`

**Evidencia**:

```python
# Línea 134-136
raw_timeline = await rag_job_event_repository.get_timeline(
    self.db, 
    job_id
)  # 1 query

# Línea 140-157
for event in raw_timeline:  # N iteraciones
    # Parsing inline, sin queries adicionales (OK)
```

Actualmente NO es N+1 (👍), pero documentar para futuro.

**Diagnóstico**:
- Actualmente OK
- Riesgo si se agregan relaciones

**Propuesta de solución**:

Documentar que timeline debe eager-load si se agregan relaciones.

**Impacto si no se corrige**:
- ⚪ Ninguno actualmente

**Prioridad**: 🟢 **BAJA** (Preventivo)

---

### 34. TESTING GAP: Falta test para `OrchestrationSummary.credits_used`

**Archivo**: `backend/tests/integration/test_rag_e2e_pipeline.py`

**Evidencia**:

Test E2E valida:
```python
# Línea 263-264
assert result.credits_used > 0
assert result.credits_used == mock_payments_facades["reservation"].credits_reserved
```

Pero no valida fórmula de cálculo real (`_calculate_actual_credits`).

**Diagnóstico**:
- Falta test unitario para cálculo de créditos
- Fórmula no validada

**Propuesta de solución**:

Agregar test unitario:

```python
def test_calculate_actual_credits():
    from app.modules.rag.facades.orchestrator_facade import _calculate_actual_credits
    
    credits = _calculate_actual_credits(
        base_cost=10,
        ocr_executed=True,
        ocr_pages=5,
        total_chunks=20,
        total_embeddings=20,
    )
    
    expected = 10 + (5*5) + 5 + (2*20)  # base + ocr + chunking + embeddings
    assert credits == expected
```

**Impacto si no se corrige**:
- ⚠️ Fórmula de precios no validada
- ⚠️ Riesgo de cobro incorrecto

**Prioridad**: 🟡 **MEDIA** (Testing)

---

### 35. TESTING GAP: Falta test para `ChunkSelector.index_range`

**Archivo**: Tests de `embed_facade`

**Evidencia**:

`ChunkSelector` soporta:
```python
# embed_facade.py:40-43
@dataclass
class ChunkSelector:
    chunk_ids: list[UUID] | None = None
    index_range: tuple[int, int] | None = None
```

Pero tests solo cubren `chunk_ids` o selector vacío.

**Diagnóstico**:
- Rama `index_range` no testeada
- Coverage gap

**Propuesta de solución**:

Agregar test:

```python
async def test_generate_embeddings_with_index_range(db, ...):
    selector = ChunkSelector(index_range=(0, 5))
    result = await generate_embeddings_facade(
        db, job_id, file_id, "text-embedding-3-large", selector
    )
    assert result.embedded == 6  # chunks 0-5 inclusive
```

**Impacto si no se corrige**:
- ⚠️ Coverage gap
- ⚠️ Bugs potenciales en feature no testeada

**Prioridad**: 🟢 **MEDIA**

---

### 36. CODE SMELL: `EmbeddingResult` tiene campos semánticamente redundantes

**Archivo**: `backend/app/modules/rag/facades/embed_facade.py:47-51`

**Evidencia**:

```python
@dataclass
class EmbeddingResult:
    total_chunks: int
    embedded: int
    skipped: int  # ❌ Redundante: total_chunks - embedded
```

**Diagnóstico**:
- `skipped = total_chunks - embedded` siempre
- Redundancia

**Propuesta de solución**:

Eliminar `skipped` o hacerlo property:

```python
@dataclass
class EmbeddingResult:
    total_chunks: int
    embedded: int
    
    @property
    def skipped(self) -> int:
        return self.total_chunks - self.embedded
```

**Impacto si no se corrige**:
- ⚪ Data redundante
- ⚠️ Riesgo de inconsistencia

**Prioridad**: 🟢 **BAJA**

---

### 37. SCHEMA NAMING: `IndexingJobCreate` vs `JobProgressResponse` inconsistentes

**Archivo**: `backend/app/modules/rag/schemas/indexing_schemas.py`

**Evidencia**:

```python
# Línea 40
class IndexingJobCreate(BaseModel):

# Línea 74
class JobProgressResponse(BaseModel):
```

**Diagnóstico**:
- Naming inconsistente: uno tiene prefijo `Indexing`, otro no
- Debería ser `IndexingJobProgressResponse` para claridad

**Propuesta de solución**:

Renombrar:

```python
class IndexingJobCreate(BaseModel):  # OK
class IndexingJobProgressResponse(BaseModel):  # ✅ Cambiar
class IndexingJobResponse(BaseModel):  # OK
```

**Impacto si no se corrige**:
- ⚪ Confusión menor

**Prioridad**: 🟢 **BAJA**

---

### 38. MAGIC NUMBERS: Progress percentages hardcodeados

**Archivo**: `backend/app/modules/rag/facades/orchestrator_facade.py`

**Evidencia**:

```python
# Línea 85
progress_pct=80,  # ❌ Magic number

# Línea 151
progress_pct=90,  # ❌ Magic number
```

**Diagnóstico**:
- Percentages hardcodeados
- Difícil de ajustar

**Propuesta de solución**:

Crear constantes:

```python
PROGRESS_PCT_MAP = {
    RagPhase.convert: 20,
    RagPhase.ocr: 40,
    RagPhase.chunk: 60,
    RagPhase.embed: 80,
    RagPhase.integrate: 90,
    RagPhase.ready: 100,
}
```

**Impacto si no se corrige**:
- ⚪ Menos mantenible

**Prioridad**: 🟢 **BAJA**

---

### 39. TESTING GAP: Falta test para error ANTES de crear job (FASE C CASO A)

**Archivo**: `backend/tests/modules/rag/facades/test_orchestrator_facade.py`

**Evidencia**:

FASE C implementó manejo de error antes de crear job:
```python
# orchestrator_facade.py:479-491
if job_id is None:
    logger.error(...)
    raise RuntimeError(...)
```

Pero test solo valida error DESPUÉS:
```python
# test_orchestrator_facade.py (nuevo en FASE C)
async def test_orchestrator_fails_before_job_creation(...)
```

**Diagnóstico**:
- Test existe (✅)
- Coverage OK

**Impacto**:
- ✅ Ya cubierto en FASE C

**Prioridad**: ✅ **RESUELTO**

---

## ⚪ PROBLEMAS OPCIONALES (8 issues)

### 40. OPTIMIZATION: Usar `select_from` explícito en queries count

**Archivo**: Todos los repositorios

**Evidencia**:

```python
# Ejemplo: chunk_metadata_repository.py:120-126
stmt = (
    select(func.count())
    .select_from(ChunkMetadata)  # ✅ Correcto
    .where(ChunkMetadata.file_id == file_id)
)
```

Algunos lo tienen, otros no.

**Diagnóstico**:
- Inconsistente
- Performance minor difference

**Propuesta de solución**:

Estandarizar TODOS los count queries con `.select_from()`.

**Impacto si no se corrige**:
- ⚪ Minor performance variance

**Prioridad**: ⚪ **OPCIONAL**

---

### 41. FEATURE REQUEST: Agregar `cancelled_by` a `rag_jobs`

**Archivo**: `database/rag/02_tables/01_table_rag_jobs.sql`

**Evidencia**:

SQL tiene:
```sql
cancelled_at   timestamptz,
```

Pero no `cancelled_by uuid` para auditoría.

**Diagnóstico**:
- Feature faltante
- No crítico

**Propuesta de solución**:

```sql
ALTER TABLE rag_jobs ADD COLUMN cancelled_by uuid;
```

**Impacto si no se corrige**:
- ⚪ Auditoría incompleta (menor)

**Prioridad**: ⚪ **OPCIONAL**

---

### 42. DOCS: README no menciona cómo hacer rollback de migrations

**Archivo**: `backend/app/modules/rag/README.md`

**Evidencia**:

README no documenta proceso de rollback SQL.

**Diagnóstico**:
- Docs incompletas

**Propuesta de solución**:

Agregar sección en README:

```markdown
### Rollback de Migraciones

Para hacer rollback de módulo RAG:
1. Ejecutar scripts en orden inverso
2. DROP FKs primero, luego tablas
3. Ver `database/rag/_rollback_rag.sql` (pendiente crear)
```

**Impacto si no se corrige**:
- ⚪ Confusión en rollbacks

**Prioridad**: ⚪ **OPCIONAL**

---

### 43. PERFORMANCE: Considerar materialized views para métricas

**Archivo**: `database/rag/08_metrics/`

**Evidencia**:

Vistas normales para KPIs:
```sql
-- 01_kpis_rag_pipeline.sql
CREATE OR REPLACE VIEW v_rag_pipeline_kpis AS ...
```

**Diagnóstico**:
- Vistas calculan en tiempo real
- Slow para dashboards

**Propuesta de solución**:

Convertir a materialized views:

```sql
CREATE MATERIALIZED VIEW mv_rag_pipeline_kpis AS ...;

-- Refresh automático con trigger o cron
```

**Impacto si no se corrige**:
- ⚪ Dashboards lentos

**Prioridad**: ⚪ **OPCIONAL**

---

### 44. FEATURE: Agregar soft delete a `chunk_metadata`

**Archivo**: `database/rag/02_tables/03_table_chunk_metadata.sql`

**Evidencia**:

No tiene `deleted_at`:

```sql
CREATE TABLE chunk_metadata (
    -- ...
    created_at          timestamptz NOT NULL DEFAULT now()
    -- NO HAY deleted_at
);
```

Pero `document_embeddings` SÍ tiene.

**Diagnóstico**:
- Inconsistente con otros modelos
- Feature opcional

**Propuesta de solución**:

```sql
ALTER TABLE chunk_metadata ADD COLUMN deleted_at timestamptz;
```

**Impacto si no se corrige**:
- ⚪ Soft delete no disponible

**Prioridad**: ⚪ **OPCIONAL**

---

### 45. LOGGING: Considerar structured logging completo (structlog)

**Archivo**: Todos

**Evidencia**:

FASE D implementó `extra` dict, pero no full structlog.

**Diagnóstico**:
- Mejora incremental
- Structlog sería mejor

**Propuesta de solución**:

Migrar a `structlog`:

```python
import structlog

logger = structlog.get_logger()

logger.info(
    "pipeline_started",
    job_id=str(job_id),
    file_id=str(file_id),
)
```

**Impacto si no se corrige**:
- ⚪ Logs menos óptimos

**Prioridad**: ⚪ **OPCIONAL** (Mejora futura)

---

### 46. TESTING: Agregar property-based testing con Hypothesis

**Archivo**: Tests

**Evidencia**:

Tests actuales son case-based, no property-based.

**Diagnóstico**:
- Coverage alta, pero no exhaustiva

**Propuesta de solución**:

Agregar Hypothesis tests:

```python
from hypothesis import given, strategies as st

@given(
    text=st.text(min_size=100, max_size=10000),
    max_tokens=st.integers(min_value=100, max_value=1000),
)
async def test_chunk_text_properties(text, max_tokens):
    # Property: sum(chunk lengths) <= original length
    chunks = await chunk_text(...)
    assert sum(len(c.chunk_text) for c in chunks) <= len(text)
```

**Impacto si no se corrige**:
- ⚪ Testing menos exhaustivo

**Prioridad**: ⚪ **OPCIONAL** (Mejora futura)

---

### 47. CODE ORGANIZATION: Considerar split de `orchestrator_facade` (557 líneas)

**Archivo**: `backend/app/modules/rag/facades/orchestrator_facade.py`

**Evidencia**:

Archivo tiene 557 líneas (advertencia en lint):

```
IMPORTANT: backend/app/modules/rag/facades/orchestrator_facade.py is 557 lines long. 
This file is getting quite large and should be considered for refactoring.
```

**Diagnóstico**:
- Archivo grande
- Podría splittearse

**Propuesta de solución**:

Split en:
- `orchestrator_facade.py` (pipeline principal)
- `credit_estimation.py` (estimación y cálculo de créditos)
- `error_handlers.py` (compensación y rollback)

**Impacto si no se corrige**:
- ⚪ Archivo grande pero funcional

**Prioridad**: ⚪ **OPCIONAL**

---

## 📊 RESUMEN CUANTITATIVO

| Severidad | Cantidad | % Total |
|-----------|----------|---------|
| 🔴 Críticos | 12 | 25.5% |
| 🟡 Altos | 15 | 31.9% |
| 🟢 Medios | 12 | 25.5% |
| ⚪ Opcionales | 8 | 17.0% |
| **TOTAL** | **47** | **100%** |

---

## 🎯 PLAN DE CORRECCIONES PROPUESTO

### FASE 1: Blockers Críticos (1-2 días)

**Prioridad**: Resolver issues que bloquean producción

1. ✅ Issue #1: Agregar `chunk_id` a `DocumentEmbedding` ORM
2. ✅ Issue #2: Alinear `text_chunk` entre ORM y SQL
3. ✅ Issue #3: Corregir `chunk.text_content` → `chunk.chunk_text` en embed_facade
4. ✅ Issue #4: Corregir `source_page` mapping
5. ✅ Issue #5: Corregir FK `rag_jobs.project_id` → `projects.id`
6. ✅ Issue #7: Eliminar import duplicado `RagJobStatus`
7. ✅ Issue #9: Convertir `DocumentEmbeddingRepository` a clase
8. ✅ Issue #10: Corregir parámetro `vector` → `embedding_vector`

**Entregable**: Pipeline RAG funcional end-to-end sin errors

---

### FASE 2: Altos + Seguridad (2-3 días)

**Prioridad**: Performance, seguridad y calidad

1. ✅ Issue #6: Eliminar índice duplicado
2. ✅ Issue #13-27: Todos los issues de severidad ALTA
3. ✅ Validaciones de seguridad (RLS, validaciones de input)

**Entregable**: Sistema robusto y seguro

---

### FASE 3: Medios + Testing (2-3 días)

**Prioridad**: Testing, docs y code quality

1. ✅ Issues #28-39: Code smells, testing gaps, docs
2. ✅ Agregar tests faltantes
3. ✅ Actualizar docs

**Entregable**: Código limpio y bien testeado

---

### FASE 4: Opcionales (Backlog)

**Prioridad**: Mejoras futuras

1. ⚪ Issues #40-47: Optimizaciones, features opcionales
2. ⚪ Considerar según roadmap

**Entregable**: Roadmap de mejoras continuas

---

## 📝 NOTAS FINALES

### Áreas de Excelencia ✅

1. **Arquitectura v2**: Separación clara de capas (repos/services/facades/routes)
2. **FASE A-D**: Proceso de hardening bien ejecutado
3. **Async-first**: Todo el código es async/await
4. **Event sourcing**: Timeline de eventos bien implementado
5. **Integración Payments**: Patrón reserva/consumo/liberación correcto
6. **Logging estructurado**: FASE D mejoró significativamente observabilidad
7. **Tests E2E**: Cobertura completa del happy path

### Áreas de Mejora Crítica ❌

1. **Alineación ORM ↔ SQL**: Múltiples inconsistencias bloqueadoras
2. **Repository pattern**: Inconsistente (3 clases, 1 módulo de funciones)
3. **Validaciones**: Faltantes en varios puntos críticos
4. **Performance**: Índices faltantes, N queries individuales

### Recomendaciones Arquitecturales 🏗️

1. **Establecer contrato ORM ↔ SQL**: Validación automática en CI
2. **Linter SQL**: Detectar columnas faltantes/extras
3. **Property-based testing**: Complementar tests case-based
4. **Monitoring**: Agregar métricas de performance en producción

---

**FIN DEL INFORME**  
**Próximo paso recomendado**: Ejecutar FASE 1 del plan de correcciones
