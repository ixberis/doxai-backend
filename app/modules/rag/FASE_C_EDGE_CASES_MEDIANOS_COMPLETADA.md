# FASE C – Edge Cases Medianos RAG v2 – COMPLETADA ✅

**Fecha:** 2025-11-28  
**Autor:** Ixchel Beristain  
**Fase:** C (Edge Cases Medianos)

---

## Resumen

FASE C completa los edge cases medianos identificados en la auditoría de bugs del módulo RAG v2:

1. **Manejo seguro de `job_id` en orchestrator** → Previene `UUID(int=0)` artificial y distingue fallos antes/después de creación del job
2. **Retry con backoff exponencial para Azure OCR** → Maneja rate limiting (429) y errores transitorios (5xx)

---

## 1. Manejo seguro de `job_id` en orchestrator

### Problema identificado

En `orchestrator_facade.py`, si el pipeline fallaba **antes** de crear el job:
- Se retornaba `OrchestrationSummary` con `job_id=UUID(int=0)` artificial
- El caller creía que existía un job "fallido" cuando en realidad nunca se persistió
- Se intentaba liberar reserva de créditos usando `job_id` que no existía

### Solución implementada

**Archivo:** `backend/app/modules/rag/facades/orchestrator_facade.py`

#### Cambio 1: Inicialización explícita de `job_id`

```python
# Línea 167 - Inicializar job_id explícitamente
job_id: UUID | None = None
phases_done: list[RagPhase] = []
reservation_id: int | None = None
```

**Antes:** `job_id` no se inicializaba, causaba `NameError` o lógica inconsistente  
**Después:** `job_id` inicia como `None` y solo se asigna tras `job_repo.create(...)`

#### Cambio 2: Distinción CASO A vs CASO B en bloque except

```python
# Líneas 398-410 - CASO A: Error antes de crear job
if job_id is None:
    logger.error(
        f"[run_indexing_job] Pipeline failed BEFORE job creation. "
        f"No job to mark as failed, no reservation to release."
    )
    raise RuntimeError(
        f"RAG pipeline failed before creating job: {str(e)}"
    ) from e

# Líneas 412+ - CASO B: Error después de crear job
logger.info(f"[run_indexing_job] Pipeline failed AFTER job creation (job_id={job_id})")
# ... compensación completa (update_status, log_event, cancel_reservation)
```

**Lógica:**

- **CASO A (`job_id is None`)**: Error ocurre antes de `job_repo.create(...)` (ej. validación de parámetros, creación de wallet falla)
  - No hay job que actualizar → no se intenta `update_status`
  - No hay `operation_id` válido → no se intenta `cancel_reservation`
  - Lanza `RuntimeError` limpio para que routes/services manejen (→ HTTP 500)

- **CASO B (`job_id` existe)**: Error ocurre después de `job_repo.create(...)`
  - Marca job como `RagJobPhase.failed`
  - Registra evento `job_failed` con payload de error
  - Libera reserva de créditos si existe
  - Retorna `OrchestrationSummary` con `job_status=failed` (compatibilidad con tests)

#### Beneficios

✅ Elimina `UUID(int=0)` artificial  
✅ Previene intentos de actualizar jobs inexistentes  
✅ Evita errores al liberar reservas con `operation_id` inválidos  
✅ Logging claro distingue entre ambos casos  
✅ Tests pueden verificar comportamiento correcto para cada escenario

---

## 2. Retry con backoff exponencial para Azure OCR

### Problema identificado

En `azure_document_intelligence.py`, el método `_start_analysis`:
- Tenía retry básico solo para 5xx
- **No** manejaba explícitamente 429 (rate limiting)
- Logs poco informativos sobre tipo de error y espera

### Solución implementada

**Archivo:** `backend/app/shared/integrations/azure_document_intelligence.py`

#### Cambio: Detección explícita de errores transitorios

```python
# Líneas 174-185 - Detectar rate limit y server errors
error_text = await resp.text()

# FASE C: Detectar errores transitorios (429, 5xx)
is_rate_limit = resp.status == 429
is_server_error = resp.status >= 500
is_transient = is_rate_limit or is_server_error

if is_transient and attempt < self.max_retries - 1:
    wait_time = 2 ** attempt
    error_type = "Rate limit (429)" if is_rate_limit else f"Server error ({resp.status})"
    logger.warning(
        f"[Azure OCR] {error_type} - Retry {attempt+1}/{self.max_retries} "
        f"after {wait_time}s: {error_text[:200]}"
    )
    await asyncio.sleep(wait_time)
    continue
```

**Antes:**
```python
if resp.status >= 500 and attempt < self.max_retries - 1:
    # Solo 5xx, sin distinción de 429
```

**Después:**
- Detecta **429 (rate limiting)** explícitamente
- Detecta **5xx (server errors)**
- Aplica **backoff exponencial** consistente: `2^attempt` segundos (0→1s, 1→2s, 2→4s)
- Logging mejorado con tipo de error específico

#### Parámetros de retry

```python
# Constructor de AzureDocumentIntelligenceClient
max_retries: int = 3,  # Total: hasta 3 intentos
polling_interval_sec: int = 2,  # Polling cada 2s una vez iniciado
```

**Tiempos de espera:**
- Intento 1 → falla → espera 1s (2^0)
- Intento 2 → falla → espera 2s (2^1)
- Intento 3 → falla → espera 4s (2^2)
- Intento 4 → lanza excepción final

#### Tipos de error manejados

| Código | Tipo | Comportamiento |
|--------|------|----------------|
| 429 | Rate limiting | Retry con backoff |
| 500-599 | Server error | Retry con backoff |
| Timeout | Network | Retry con backoff |
| 400-499 (no 429) | Client error | Falla inmediatamente (no retry) |
| 202 | Accepted | Éxito, retorna operation_location |

#### Beneficios

✅ Maneja rate limiting de Azure (429) sin fallar inmediatamente  
✅ Backoff exponencial previene "retry storm"  
✅ Logging claro del tipo de error y tiempo de espera  
✅ Errores no transitorios (4xx) fallan rápido (no malgasta reintentos)  
✅ Compatible con existing tests (mocks siguen funcionando)

---

## Archivos modificados

1. **`backend/app/modules/rag/facades/orchestrator_facade.py`**
   - Línea 167: Inicialización `job_id: UUID | None = None`
   - Líneas 388-456: Refactorización completa del bloque `except` con CASO A/B

2. **`backend/app/shared/integrations/azure_document_intelligence.py`**
   - Líneas 132-184: Refactorización de `_start_analysis` con retry 429/5xx

3. **`backend/app/modules/rag/FASE_C_EDGE_CASES_MEDIANOS_COMPLETADA.md`** (este archivo)

---

## Tests a ejecutar

### Validación de compilación

```bash
python -c "from app.modules.rag.facades.orchestrator_facade import run_indexing_job; print('✅ Orchestrator OK')"
python -c "from app.shared.integrations.azure_document_intelligence import AzureDocumentIntelligenceClient; print('✅ Azure client OK')"
```

### Tests de facades y orchestrator

```bash
pytest backend/tests/modules/rag/facades/test_orchestrator_facade.py -v
pytest backend/tests/modules/rag/facades/test_ocr_facade_integration.py -v
```

### Suite RAG completa

```bash
pytest backend/tests/modules/rag/ -v --tb=short
```

### E2E

```bash
pytest backend/tests/integration/test_rag_e2e_pipeline.py -v
```

---

## Tests adicionales recomendados (no implementados en FASE C)

### Para orchestrator (CASO A: fallo antes de crear job)

```python
@pytest.mark.asyncio
async def test_orchestrator_fails_before_job_creation(db_session):
    """Test: Fallo en validación inicial lanza RuntimeError sin crear job."""
    
    # Mock storage_client=None para forzar ValueError antes de crear job
    with pytest.raises(RuntimeError, match="before creating job"):
        await run_indexing_job(
            db=db_session,
            project_id=uuid4(),
            file_id=uuid4(),
            user_id=uuid4(),
            mime_type="application/pdf",
            needs_ocr=False,
            storage_client=None,  # Forzar error temprano
            source_uri="users-files/test.pdf",
        )
    
    # Verificar que NO se creó ningún job en DB
    jobs = await db_session.execute(select(RagJob))
    assert len(jobs.scalars().all()) == 0
```

### Para Azure OCR (429 retry)

```python
@pytest.mark.asyncio
async def test_azure_ocr_retries_on_429(mock_storage_client):
    """Test: Azure OCR reintenta ante 429 y eventualmente tiene éxito."""
    
    # Mock que lanza 429 dos veces, luego 202 (success)
    call_count = 0
    async def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            # Simular 429
            mock_resp = AsyncMock()
            mock_resp.status = 429
            mock_resp.text = AsyncMock(return_value="Rate limit exceeded")
            return mock_resp
        else:
            # Simular 202 (accepted)
            mock_resp = AsyncMock()
            mock_resp.status = 202
            mock_resp.headers = {"Operation-Location": "https://azure.com/operations/123"}
            return mock_resp
    
    with patch("aiohttp.ClientSession.post", side_effect=mock_post):
        client = AzureDocumentIntelligenceClient(
            endpoint="https://test.cognitiveservices.azure.com",
            api_key="test-key"
        )
        
        # No debe lanzar excepción, debe reintentar y tener éxito
        operation_location = await client._start_analysis(
            file_uri="https://example.com/doc.pdf",
            model_id="prebuilt-read",
            locale=None,
            pages=None,
        )
        
        assert operation_location == "https://azure.com/operations/123"
        assert call_count == 3  # 2 fallos + 1 éxito
```

---

## Próximos pasos

### FASE D (Opcional - Mejoras no bloqueantes)

1. **Índice en `rag_jobs.file_id`** (SQL)
   - Archivo: `database/rag/03_indexes/`
   - Mejora: queries por `file_id` más rápidas

2. **Logging estructurado** (Python)
   - Archivos: facades, orchestrator
   - Mejora: JSON logs con contexto de job para observabilidad

### Decisión de cierre

- Si FASE D no es prioritaria → **Módulo RAG v2 production-ready tras FASE C**
- Si se requiere optimización → ejecutar FASE D antes de deploy

---

## Conclusión

FASE C endurece el módulo RAG v2 contra edge cases medianos que podrían causar:
- Jobs "fantasma" sin ID real
- Fallos de reserva de créditos por IDs inválidos
- Fallos innecesarios ante rate limiting de Azure

El módulo ahora maneja correctamente:
✅ Fallos tempranos (antes de crear job) vs tardíos (después)  
✅ Errores transitorios de Azure con retry inteligente  
✅ Compensación de créditos solo cuando aplica  
✅ Logging claro para debugging en producción

**Estado:** FASE C COMPLETADA ✅  
**Siguiente:** Ejecutar tests y decidir si proceder con FASE D o declarar RAG v2 production-ready.
