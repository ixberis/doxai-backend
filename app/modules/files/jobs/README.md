# Files Jobs Module

Este directorio contiene los jobs programados del módulo Files.

## Jobs Incluidos

### 1. `reconcile_ghost_files_job`

**Propósito**: Detecta y archiva "ghost files" (registros en DB sin archivo físico en storage).

**Configuración**:
- `FILES_RECONCILE_GHOSTS_ENABLED`: Habilita/deshabilita (default: `true`)
- `FILES_RECONCILE_GHOSTS_INTERVAL_HOURS`: Intervalo de ejecución (default: `6`)
- `FILES_RECONCILE_GHOSTS_BATCH_SIZE`: Archivos por batch (default: `100`)

### 2. `retention_cleanup_job`

**Propósito**: Implementa la política de retención de archivos (RFC-DoxAI-RET-001).

**Flujo**:
1. **Fase Grace**: Proyectos `closed` con `ready_at` anterior al umbral → transición a `retention_grace`
2. **Fase Delete**: Proyectos `retention_grace` con `ready_at` anterior al umbral total → eliminación física + `deleted_by_policy`

**SSOT (Sin columnas nuevas)**:
- `projects.project_status`: Estado del proyecto (`closed` → `retention_grace` → `deleted_by_policy`)
- **`projects.ready_at`**: Timestamp canónico para inicio de retención (NO usar closed_at, retention_grace_at, etc.)
- `input_files.storage_state` / `product_files.storage_state`: `present` → `missing` (invalidación lógica)

**Configuración**:
- `FILES_RETENTION_ENABLED`: Habilita/deshabilita (default: `true`)
- `FILES_RETENTION_INTERVAL_HOURS`: Intervalo de ejecución (default: `24`)
- `FILES_RETENTION_GRACE_DAYS`: Días hasta `retention_grace` (default: `30`)
- `FILES_RETENTION_DELETE_DAYS`: Días adicionales hasta eliminación (default: `60`)
- `FILES_RETENTION_BATCH_SIZE`: Proyectos por batch (default: `100`)

**Ejemplo de Timeline**:
```
ready_at = 2026-01-01 (proyecto marcado como 'closed')
grace_days = 30
delete_days = 60

2026-01-01: Proyecto cerrado, ready_at = now()
2026-01-31: Proyecto transiciona a 'retention_grace' (30 días desde ready_at)
2026-03-02: Archivos eliminados, proyecto = 'deleted_by_policy' (90 días desde ready_at)
```

**Características**:
- **Idempotente**: Archivos no encontrados se tratan como éxito
- **Batch processing**: Procesa por proyecto con commit por batch
- **dry_run**: Modo simulación sin modificar datos
- **Storage API**: Usa `SupabaseStorageHTTPClient.delete_file()` (HTTP API, no SQL a storage.objects)
- **Auditoría**: Registra ejecución en `kpis.job_executions`
- **Sin columnas nuevas**: Usa `ready_at` existente como timestamp canónico

## Uso

### Registro en Scheduler

```python
from app.modules.files.jobs import (
    register_reconcile_ghost_files_job,
    register_retention_cleanup_job,
)

# En main.py o startup
register_reconcile_ghost_files_job()
register_retention_cleanup_job()
```

### Ejecución Manual (dry_run)

```python
from app.modules.files.jobs import retention_cleanup_job

# Simular sin modificar datos
stats = await retention_cleanup_job(dry_run=True)
print(stats)
```

### Ejecución Manual (real)

```python
# ⚠️ PRECAUCIÓN: Modifica datos reales
stats = await retention_cleanup_job(
    dry_run=False,
    grace_days=30,
    delete_days=60,
    batch_size=50
)
```

## Tests

```bash
# Ejecutar tests CI-safe
pytest tests/modules/files/jobs/ -v
```

## Dependencias

- `app.shared.utils.http_storage_client.SupabaseStorageHTTPClient`
- `app.shared.observability.JobExecutionTracker`
- `app.shared.scheduler.SchedulerService`

## Git Commits Propuestos

```bash
# Corrección de schema (revertir columnas nuevas)
git add database/projects/02_tables/01_projects.sql
git commit -m "fix(projects): remove unapproved retention columns, use ready_at as SSOT"

# Job de retención corregido
git add backend/app/modules/files/jobs/retention_cleanup_job.py
git add backend/app/modules/files/jobs/README.md
git commit -m "fix(files): retention job uses ready_at and Storage API (not SQL)"

# Tests actualizados
git add backend/tests/modules/files/jobs/
git commit -m "test(files): verify retention job uses ready_at, not new columns"
```
