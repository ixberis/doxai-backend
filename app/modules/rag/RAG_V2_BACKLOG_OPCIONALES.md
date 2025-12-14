# 📋 RAG v2 – BACKLOG DE MEJORAS OPCIONALES

**Fecha**: 2025-11-28  
**Base**: Auditoría integral RAG v2 (`AUDIT_RAG_V2_INTEGRAL.md`)  
**Estado**: Documentado para futuro (NO implementado)

---

## 🎯 Propósito de este Backlog

Este documento contiene **mejoras opcionales** identificadas en la auditoría integral del módulo RAG v2 que:

- ✅ Son mejoras de calidad, no blockers
- ✅ Tienen beneficio claro pero no son urgentes
- ✅ Pueden implementarse cuando roadmap lo permita
- ✅ No afectan funcionalidad core si no se hacen

**Importante**: Estos issues NO son críticos ni altos. El módulo RAG funciona correctamente sin ellos.

---

## 📊 Resumen Cuantitativo

| Categoría | Cantidad | Prioridad |
|-----------|----------|-----------|
| Performance | 2 | Media |
| Features | 2 | Baja |
| Testing | 1 | Baja |
| Logging | 1 | Baja |
| Code Organization | 1 | Baja |
| Documentación | 1 | Baja |
| **TOTAL** | **8** | **Opcional** |

---

## 🟡 Issues de FASE 3 Movidos a Backlog

Estos issues eran MEDIOS pero requieren refactors grandes:

### B-1. Validación de FK en integrate_facade (Issue #31 MEDIO)

**Descripción**:
El facade `integrate_vector_index` no valida que `file_id` exista en `files_base` antes de queries.

**Beneficio esperado**:
- Errores más claros cuando file_id no existe
- Evita FK violations crípticas

**Riesgo/Impacto de hacerlo ahora**:
- Requiere dependency a módulo Files
- Cambio arquitectural (cross-module validation)
- Riesgo de introducir coupling

**Propuesta técnica**:
```python
# En integrate_facade.py
from app.modules.files.models import FilesBase

# Validar que file_id existe
file = await db.get(FilesBase, file_id)
if not file:
    raise ValueError(f"file_id {file_id} does not exist")
```

**Cuándo abordarlo**:
- Cuando se implemente **unified validation layer** cross-modules
- Cuando se refactorice patrón de validaciones en facades
- Después de tener métricas de producción para ver frecuencia del error

**Archivos afectados**:
- `backend/app/modules/rag/facades/integrate_facade.py`

---

### B-2. Helper para logging patterns duplicados (Issue #32 MEDIO)

**Descripción**:
Patrón de logging estructurado se repite en todos los facades (6 archivos):

```python
logger.info(
    "[facade_name] Starting phase",
    extra={"job_id": str(job_id), "file_id": str(file_id)},
)
```

**Beneficio esperado**:
- DRY: Cambiar logging en un lugar en vez de 6
- Consistencia garantizada
- Menos código boilerplate

**Riesgo/Impacto de hacerlo ahora**:
- Requiere tocar 6 facades (convert, ocr, chunk, embed, integrate, orchestrator)
- Riesgo de introducir bugs en logging ya funcional
- Mejora incremental, no crítica

**Propuesta técnica**:
```python
# utils/logging_helpers.py
def log_phase_start(logger, phase: RagPhase, job_id: UUID, **extra):
    logger.info(
        f"[{phase.value}] Starting phase",
        extra={"job_id": str(job_id), "phase": phase.value, **extra},
    )

def log_phase_complete(logger, phase: RagPhase, job_id: UUID, **metrics):
    logger.info(
        f"[{phase.value}] Completed",
        extra={"job_id": str(job_id), "phase": phase.value, **metrics},
    )
```

**Cuándo abordarlo**:
- Junto con migración a `structlog` (Issue B-6)
- En un sprint dedicado a refactor de observabilidad
- Después de tener métricas de producción sobre logging

**Archivos afectados**:
- `backend/app/modules/rag/facades/*.py` (6 archivos)
- `backend/app/modules/rag/utils/logging_helpers.py` (nuevo)

---

### B-3. Magic numbers en progress_pct (Issue #38 MEDIO)

**Descripción**:
Percentages de progreso hardcodeados en múltiples lugares:

```python
# orchestrator_facade.py:85
progress_pct=80,  # ❌ Magic number

# orchestrator_facade.py:151
progress_pct=90,  # ❌ Magic number
```

**Beneficio esperado**:
- Fácil de ajustar porcentajes de progreso
- Centralizado en constantes
- Más mantenible

**Riesgo/Impacto de hacerlo ahora**:
- Requiere centralizar en módulo constants
- Actualizar 3+ archivos (orchestrator, indexing_service)
- No es blocker, UX funciona

**Propuesta técnica**:
```python
# constants.py
PROGRESS_PCT_MAP = {
    RagPhase.convert: 15,
    RagPhase.ocr: 35,
    RagPhase.chunk: 55,
    RagPhase.embed: 75,
    RagPhase.integrate: 90,
    RagPhase.ready: 100,
}

# Usar en facades:
progress_pct = PROGRESS_PCT_MAP[current_phase]
```

**Cuándo abordarlo**:
- En un sprint de UX improvements
- Cuando se revise experiencia de progreso con usuarios
- Junto con refactor de IndexingService (Issue B-7)

**Archivos afectados**:
- `backend/app/modules/rag/facades/orchestrator_facade.py`
- `backend/app/modules/rag/services/indexing_service.py`
- `backend/app/modules/rag/constants.py` (nuevo)

---

## ⚪ Issues OPCIONALES de Auditoría (FASE 4)

### B-4. Usar select_from explícito en queries count (Issue #40)

**Descripción**:
Algunos repositorios usan `select_from` en count queries, otros no:

```python
# ✅ Con select_from (explícito)
stmt = (
    select(func.count())
    .select_from(ChunkMetadata)
    .where(ChunkMetadata.file_id == file_id)
)

# ❌ Sin select_from (implícito)
stmt = (
    select(func.count())
    .where(ChunkMetadata.file_id == file_id)
)
```

**Beneficio esperado**:
- Consistencia en código
- Query plan más predecible
- Minor performance improvement (marginal)

**Riesgo/Impacto de hacerlo ahora**:
- Cambio cosmético
- Riesgo bajo pero beneficio marginal

**Propuesta técnica**:
Estandarizar TODOS los count queries con `.select_from()` explícito.

**Cuándo abordarlo**:
- En sprint de code quality improvements
- Junto con revisión de performance queries
- No urgente

**Archivos afectados**:
- Todos los repositorios (4 archivos)

**Prioridad**: ⚪ **OPCIONAL** (Baja)

---

### B-5. Agregar cancelled_by a rag_jobs (Issue #41)

**Descripción**:
Tabla `rag_jobs` tiene `cancelled_at` pero no `cancelled_by` para auditoría.

**Beneficio esperado**:
- Auditoría completa de cancelaciones
- Saber quién canceló un job

**Riesgo/Impacto de hacerlo ahora**:
- Feature nueva, no crítica
- Requiere migración SQL
- No hay requerimiento de negocio actual

**Propuesta técnica**:
```sql
ALTER TABLE rag_jobs ADD COLUMN cancelled_by uuid;
ALTER TABLE rag_jobs ADD CONSTRAINT fk_rag_jobs_cancelled_by
    FOREIGN KEY (cancelled_by) REFERENCES app_users(user_id);
```

**Cuándo abordarlo**:
- Cuando haya requerimiento de negocio para auditar cancelaciones
- Junto con feature de "quién hizo qué" en jobs
- No antes de tener UI de gestión de jobs

**Archivos afectados**:
- `database/rag/02_tables/01_table_rag_jobs.sql`
- `backend/app/modules/rag/models/job_models.py`

**Prioridad**: ⚪ **OPCIONAL** (Baja)

---

### B-6. Migrar logging a structlog (Issue #45)

**Descripción**:
FASE D implementó logging estructurado con `extra` dict, pero `structlog` sería mejor:

```python
# Actual (FASE D)
logger.info(
    "[phase] Message",
    extra={"job_id": str(job_id), "file_id": str(file_id)},
)

# Con structlog (propuesta)
logger.info(
    "phase_started",
    job_id=str(job_id),
    file_id=str(file_id),
)
```

**Beneficio esperado**:
- Logging más estructurado
- Mejor integración con herramientas (Datadog, Splunk)
- Parsing más fácil

**Riesgo/Impacto de hacerlo ahora**:
- Requiere agregar dependency (`structlog`)
- Refactor de TODOS los logs (50+ líneas)
- Riesgo de romper logging en producción

**Propuesta técnica**:
```python
# Agregar dependency
pip install structlog

# Configurar en app startup
import structlog
structlog.configure(...)

# Usar en facades
logger = structlog.get_logger()
logger.info("pipeline_started", job_id=str(job_id), phase="convert")
```

**Cuándo abordarlo**:
- En un sprint dedicado a observabilidad
- Después de tener métricas de producción de logs
- Junto con integración de herramientas de agregación (Datadog)

**Archivos afectados**:
- Todos los facades, services, routes (20+ archivos)
- `backend/app/shared/logging/` (nueva configuración)

**Prioridad**: ⚪ **OPCIONAL** (Media, mejora futura)

---

### B-7. Split de orchestrator_facade.py (Issue #47)

**Descripción**:
Archivo `orchestrator_facade.py` tiene 557 líneas (advertencia en lint).

**Beneficio esperado**:
- Archivo más pequeño y fácil de navegar
- Separación de concerns más clara

**Riesgo/Impacto de hacerlo ahora**:
- Refactor grande (split en 3 archivos)
- Riesgo de romper imports
- Archivo funciona bien, solo es largo

**Propuesta técnica**:
Split en:
- `orchestrator_facade.py` (pipeline principal, 200 líneas)
- `credit_estimation.py` (estimación y cálculo de créditos, 100 líneas)
- `error_handlers.py` (compensación y rollback, 150 líneas)
- `orchestrator_types.py` (dataclasses, 100 líneas)

**Cuándo abordarlo**:
- En un sprint de refactor de código
- Cuando archivo exceda 700 líneas
- Junto con revisión de arquitectura de facades

**Archivos afectados**:
- `backend/app/modules/rag/facades/orchestrator_facade.py` (split)
- Todos los imports a orchestrator (tests, routes)

**Prioridad**: ⚪ **OPCIONAL** (Baja, código funcional)

---

### B-8. Property-based testing con Hypothesis (Issue #46)

**Descripción**:
Tests actuales son case-based, no property-based.

**Beneficio esperado**:
- Cobertura más exhaustiva
- Encontrar edge cases no anticipados

**Riesgo/Impacto de hacerlo ahora**:
- Requiere agregar dependency (`hypothesis`)
- Curva de aprendizaje para equipo
- Tests actuales ya tienen 90%+ coverage

**Propuesta técnica**:
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

**Cuándo abordarlo**:
- En un sprint de testing improvements
- Después de tener experiencia con Hypothesis en otro módulo
- Cuando coverage baje de 85%

**Archivos afectados**:
- `backend/tests/modules/rag/` (agregar tests de properties)

**Prioridad**: ⚪ **OPCIONAL** (Baja, mejora incremental)

---

### B-9. Considerar materialized views para métricas (Issue #43)

**Descripción**:
Vistas normales para KPIs calculan en tiempo real:

```sql
-- Actual
CREATE OR REPLACE VIEW v_rag_pipeline_kpis AS ...

-- Propuesta
CREATE MATERIALIZED VIEW mv_rag_pipeline_kpis AS ...;
```

**Beneficio esperado**:
- Dashboards más rápidos
- Queries de métricas pre-calculadas

**Riesgo/Impacto de hacerlo ahora**:
- Requiere strategy de refresh (trigger o cron)
- Datos pueden estar desactualizados
- No hay requerimiento de performance actual

**Propuesta técnica**:
```sql
CREATE MATERIALIZED VIEW mv_rag_pipeline_kpis AS ...;

-- Refresh automático con trigger o cron
CREATE OR REPLACE FUNCTION refresh_rag_kpis()
RETURNS TRIGGER AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_rag_pipeline_kpis;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
```

**Cuándo abordarlo**:
- Cuando dashboards tengan > 2 segundos de latencia
- En un sprint de performance optimization
- Después de tener métricas de usage de vistas

**Archivos afectados**:
- `database/rag/08_metrics/*.sql`

**Prioridad**: ⚪ **OPCIONAL** (Media, solo si performance es problema)

---

### B-10. Documentación de rollback de migraciones (Issue #42)

**Descripción**:
README no documenta proceso de rollback SQL.

**Beneficio esperado**:
- Proceso de rollback claro
- Evita confusión en emergencias

**Riesgo/Impacto de hacerlo ahora**:
- Solo documentación
- No afecta código

**Propuesta técnica**:
Agregar sección en `README.md`:

```markdown
### Rollback de Migraciones

Para hacer rollback del módulo RAG:

1. Ejecutar scripts en orden inverso:
   - DROP FKs primero (`12_foreign_keys_rag.sql` inverso)
   - DROP tablas (`01-11_*.sql` inverso)
   - DROP tipos ENUMs (`01_enums_rag.sql` inverso)

2. Script de rollback automático:
   ```bash
   psql -U postgres -d your_db -f database/rag/_rollback_rag.sql
   ```

3. Verificar limpieza:
   ```sql
   SELECT * FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE 'rag_%';
   ```
```

**Cuándo abordarlo**:
- En un sprint de docs improvements
- Antes de deployment a producción
- Junto con revisión de proceso de migrations

**Archivos afectados**:
- `backend/app/modules/rag/README.md`
- `database/rag/_rollback_rag.sql` (nuevo)

**Prioridad**: ⚪ **OPCIONAL** (Baja, docs)

---

### B-11. Soft delete en chunk_metadata (Issue #44)

**Descripción**:
Tabla `chunk_metadata` no tiene `deleted_at`, pero `document_embeddings` sí.

**Beneficio esperado**:
- Consistencia entre modelos
- Soft delete disponible si se necesita

**Riesgo/Impacto de hacerlo ahora**:
- Feature opcional
- No hay requerimiento actual
- Requiere migración SQL

**Propuesta técnica**:
```sql
ALTER TABLE chunk_metadata ADD COLUMN deleted_at timestamptz;
```

**Cuándo abordarlo**:
- Cuando haya requerimiento de soft delete en chunks
- Junto con feature de "recuperar chunks borrados"
- No urgente

**Archivos afectados**:
- `database/rag/02_tables/03_table_chunk_metadata.sql`
- `backend/app/modules/rag/models/chunk_models.py`

**Prioridad**: ⚪ **OPCIONAL** (Baja)

---

## 📊 Matriz de Priorización

| Issue | Beneficio | Esfuerzo | Riesgo | Cuándo |
|-------|-----------|----------|--------|--------|
| B-1 (FK validation) | Medio | Medio | Medio | Unified validation layer |
| B-2 (Logging helper) | Medio | Alto | Medio | Con migración structlog |
| B-3 (Magic numbers) | Bajo | Bajo | Bajo | Sprint UX |
| B-4 (select_from) | Bajo | Bajo | Bajo | Code quality sprint |
| B-5 (cancelled_by) | Bajo | Bajo | Bajo | Cuando haya requerimiento |
| B-6 (structlog) | Alto | Alto | Medio | Sprint observability |
| B-7 (Split orchestrator) | Medio | Alto | Medio | Cuando >700 líneas |
| B-8 (Hypothesis) | Medio | Medio | Bajo | Testing improvements |
| B-9 (Materialized views) | Medio | Medio | Bajo | Si performance problema |
| B-10 (Docs rollback) | Bajo | Bajo | Ninguno | Antes de producción |
| B-11 (Soft delete) | Bajo | Bajo | Bajo | Cuando haya requerimiento |

---

## 🎯 Recomendaciones de Implementación

### Tier 1: Considerar en próximo sprint (Alto impacto, bajo riesgo)

- **B-10** (Docs rollback): Bajo esfuerzo, alta utilidad antes de producción

### Tier 2: Considerar en Q1 2025 (Mejoras de calidad)

- **B-3** (Magic numbers): Fácil, mejora mantenibilidad
- **B-4** (select_from): Fácil, mejora consistencia

### Tier 3: Considerar en Q2 2025 (Features opcionales)

- **B-5** (cancelled_by): Solo si hay requerimiento de negocio
- **B-11** (Soft delete): Solo si hay requerimiento de negocio

### Tier 4: Considerar en H2 2025 (Refactors grandes)

- **B-1** (FK validation): Esperar unified validation layer
- **B-2** (Logging helper): Junto con B-6
- **B-6** (structlog): Sprint dedicado de observabilidad
- **B-7** (Split orchestrator): Solo si archivo crece más
- **B-8** (Hypothesis): Mejora incremental de testing
- **B-9** (Materialized views): Solo si performance es problema

---

## 📝 Notas Finales

**Importante**: Este backlog NO es obligatorio. El módulo RAG v2 funciona correctamente sin implementar ninguno de estos issues.

**Criterio para priorizar**:
1. ¿Hay requerimiento de negocio?
2. ¿Hay problema de performance/calidad medido?
3. ¿El beneficio justifica el esfuerzo y riesgo?

**Mantener backlog actualizado**:
- Revisar cada trimestre
- Eliminar issues ya no relevantes
- Agregar nuevos issues identificados
- Re-priorizar según roadmap

---

**Documento de referencia**: Backlog FASE 4 documentado ✅  
**Próxima revisión sugerida**: Q1 2025
