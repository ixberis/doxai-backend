# FASE A – Bugs Críticos RAG v2 – COMPLETADA ✅

**Fecha**: 2025-11-28  
**Autor**: DoxAI  
**Alcance**: Corrección de 3 bugs críticos identificados en la revisión final del módulo RAG v2

---

## Resumen Ejecutivo

Se aplicaron las correcciones de FASE A del informe de bugs del módulo RAG v2, resolviendo 3 issues críticos que impedían la compilación y ejecución correcta del sistema:

1. ✅ **Bug 1.1** – Import inexistente de `RagJobStatus`
2. ✅ **Bug 1.2** – Repositorios definidos como funciones pero usados como clases
3. ✅ **Bug 1.3** – Tipo de `event_payload` inconsistente (str vs dict/JSONB)

---

## 1. Bug 1.1 – RagJobStatus Inexistente

### Problema
El schema `indexing_schemas.py` importaba `RagJobStatus` que no existe en los enums del módulo RAG, causando `ImportError` al inicializar la aplicación.

### Solución Aplicada

**Archivo**: `backend/app/modules/rag/schemas/indexing_schemas.py`

**Cambios**:
- Eliminado import de `RagJobStatus`
- Campo `status` en `JobProgressResponse` ahora usa `Optional[RagJobPhase]`
- Actualizado `field_serializer` para usar `RagJobPhase`

**Resultado**: El schema compila correctamente y usa el enum existente `RagJobPhase` para representar tanto `phase` como `status`.

---

## 2. Bug 1.2 – Repositorios como Clases

### Problema
Los repositorios `rag_job_repository.py` y `rag_job_event_repository.py` estaban definidos como módulos con funciones planas, pero el código (facades, services, __init__.py) los importaba y usaba como clases, causando `TypeError` al intentar instanciarlos.

### Solución Aplicada

**Archivos Modificados**:
- `backend/app/modules/rag/repositories/rag_job_repository.py`
- `backend/app/modules/rag/repositories/rag_job_event_repository.py`
- `backend/app/modules/rag/repositories/__init__.py`

**Cambios**:

1. **RagJobRepository** convertido a clase con métodos:
   - `async def create(self, session, *, project_id, file_id, created_by, ...)`
   - `async def get_by_id(self, session, job_id)`
   - `async def list_by_project(self, session, project_id, *, limit, offset)`
   - `async def update_phase(self, session, job_id, phase_current)`
   - `async def update_status(self, session, job_id, status)`
   - `async def update_phase_and_status(self, session, job_id, phase_current, status)`

2. **RagJobEventRepository** convertido a clase con métodos:
   - `async def log_event(self, session, *, job_id, event_type, rag_phase, progress_pct, message, event_payload)`
   - `async def get_timeline(self, session, job_id, *, limit)`
   - `async def get_latest_event(self, session, job_id)`

3. **Instancias globales** creadas para compatibilidad con código existente:
   ```python
   rag_job_repository = RagJobRepository()
   rag_job_event_repository = RagJobEventRepository()
   ```

4. **__init__.py** actualizado para exportar tanto clases como instancias:
   ```python
   __all__ = [
       "RagJobRepository",
       "rag_job_repository",
       "RagJobEventRepository", 
       "rag_job_event_repository",
       ...
   ]
   ```

**Resultado**: Los repositorios ahora son clases instanciables. El código existente que importa las instancias globales (`rag_job_repository`, `rag_job_event_repository`) sigue funcionando sin cambios.

---

## 3. Bug 1.3 – event_payload como dict/JSONB

### Problema
El campo `event_payload` en `RagJobEvent` estaba definido como `String` en el modelo ORM, pero el repositorio esperaba `str` y las facades intentaban pasar dicts, causando `TypeError` o inconsistencias al serializar/deserializar.

### Solución Aplicada

**Archivos Modificados**:
- `backend/app/modules/rag/models/job_models.py`
- `backend/app/modules/rag/repositories/rag_job_event_repository.py`
- Todas las facades que llaman `log_event` (orchestrator, chunk, integrate)

**Cambios**:

1. **Modelo ORM** (`job_models.py`):
   ```python
   from sqlalchemy.dialects.postgresql import JSONB
   
   event_payload = Column(
       JSONB,
       nullable=False,
       default=dict,
       comment="Payload JSON del evento"
   )
   ```

2. **Repository** (`rag_job_event_repository.py`):
   ```python
   async def log_event(
       self,
       session: AsyncSession,
       *,
       event_payload: Optional[dict] = None,  # dict en lugar de str
   ) -> RagJobEvent:
       event = RagJobEvent(
           ...
           event_payload=event_payload or {},
           ...
       )
   ```

3. **Facades actualizadas** para pasar dicts:
   ```python
   await rag_job_event_repository.log_event(
       db,
       job_id=job_id,
       event_type="job_completed",
       event_payload={
           "total_chunks": total_chunks,
           "total_embeddings": total_embeddings,
       }
   )
   ```

**Resultado**: El campo `event_payload` ahora usa JSONB nativo de PostgreSQL, acepta dicts en Python, y no requiere serialización manual con `json.dumps()`.

---

## 4. Cambios Adicionales en Services

**Archivo**: `backend/app/modules/rag/services/indexing_service.py`

**Cambios**:
- Eliminado import de `RagJobStatus` inexistente
- Ajustados campos al crear jobs: `created_by` en lugar de `started_by`, `status` en lugar de `phase`
- Actualizado mapeo de campos en respuestas para usar nombres correctos del ORM

---

## 5. Cambios en Facades

**Archivos Modificados**:
- `backend/app/modules/rag/facades/orchestrator_facade.py`
- `backend/app/modules/rag/facades/chunk_facade.py`
- `backend/app/modules/rag/facades/integrate_facade.py`

**Cambios**:
- Todos los imports de `from ...rag_job_event_repository import log_event` reemplazados por:
  ```python
  from ...rag_job_event_repository import rag_job_event_repository
  ```
- Todas las llamadas a `await log_event(...)` reemplazadas por:
  ```python
  await rag_job_event_repository.log_event(...)
  ```

---

## 6. Comandos de Validación

### Verificar Compilación

```bash
# Verificar que los schemas compilan
python -c "from app.modules.rag.schemas.indexing_schemas import JobProgressResponse; print('✅ Schemas OK')"

# Verificar que los repositorios se pueden importar
python -c "from app.modules.rag.repositories import RagJobRepository, RagJobEventRepository, rag_job_repository, rag_job_event_repository; print('✅ Repos OK')"

# Verificar que el modelo compila
python -c "from app.modules.rag.models.job_models import RagJobEvent; print('✅ Models OK')"
```

### Tests de Repositorios

```bash
# Tests de RagJobRepository
pytest backend/tests/modules/rag/repositories/test_rag_job_repository.py -v

# Tests de RagJobEventRepository
pytest backend/tests/modules/rag/repositories/test_rag_job_event_repository.py -v

# Todos los tests de repositorios
pytest backend/tests/modules/rag/repositories/ -v
```

### Tests de Services

```bash
# Tests de IndexingService
pytest backend/tests/modules/rag/services/test_indexing_service.py -v

# Todos los tests de services
pytest backend/tests/modules/rag/services/ -v
```

### Tests de Facades

```bash
# Tests de orchestrator_facade
pytest backend/tests/modules/rag/facades/test_orchestrator_facade.py -v

# Todos los tests de facades
pytest backend/tests/modules/rag/facades/ -v
```

### Suite Completa RAG

```bash
# Suite completa del módulo RAG
pytest backend/tests/modules/rag/ -v --tb=short

# Smoke test rápido (solo lo esencial)
pytest backend/tests/modules/rag/ -v --tb=short -x
```

---

## 7. Impacto y Migraciones

### Cambios en Base de Datos
⚠️ **IMPORTANTE**: El cambio de `event_payload` de `String` a `JSONB` requiere migración de datos si hay eventos existentes:

```sql
-- Si existen datos legacy en formato string "{...}"
UPDATE rag_job_events
SET event_payload = event_payload::jsonb
WHERE event_payload IS NOT NULL;
```

### Código Dependiente
✅ **No se requieren cambios** en código que usa las instancias globales de repositorios.

❌ **Requiere actualización** cualquier código que:
- Importe clases de repositorios para instanciar manualmente
- Llame directamente a funciones `create()`, `log_event()` sin instancia

---

## 8. Próximos Pasos

Con FASE A completada, el módulo RAG v2 está listo para:

✅ **FASE B** – Inconsistencias Altas:
- Agregar columna `needs_ocr` al modelo ORM `RagJob`
- Alinear nombres de columnas en `ChunkMetadata`
- Agregar validación de `text_uri`
- Implementar `db.rollback()` explícito en orchestrator

✅ **FASE C** – Edge Cases Medianos:
- Mejorar manejo de `job_id` en orchestrator
- Implementar retry con backoff para Azure OCR

✅ **FASE D** – Mejoras Opcionales:
- Agregar índice en `rag_jobs.file_id`
- Enriquecer logging estructurado

---

## 9. Archivos Modificados (Resumen)

### Schemas
- `backend/app/modules/rag/schemas/indexing_schemas.py`

### Modelos ORM
- `backend/app/modules/rag/models/job_models.py`

### Repositorios
- `backend/app/modules/rag/repositories/rag_job_repository.py`
- `backend/app/modules/rag/repositories/rag_job_event_repository.py`
- `backend/app/modules/rag/repositories/__init__.py`

### Services
- `backend/app/modules/rag/services/indexing_service.py`

### Facades
- `backend/app/modules/rag/facades/orchestrator_facade.py`
- `backend/app/modules/rag/facades/chunk_facade.py`
- `backend/app/modules/rag/facades/integrate_facade.py`

---

**Fin del documento FASE A**
