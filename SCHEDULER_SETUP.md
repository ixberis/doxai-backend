# Configuración del Sistema de Jobs Programados

Este documento describe cómo configurar e integrar el sistema de jobs programados con APScheduler.

## Instalación

### 1. Instalar APScheduler

Agregar a `requirements.txt`:

```
apscheduler>=3.10.4
```

O instalar directamente:

```bash
pip install apscheduler
```

## Integración con FastAPI

### 2. Modificar main.py

Agregar el scheduler al ciclo de vida de la aplicación:

```python
# backend/app/main.py

from fastapi import FastAPI
from contextlib import asynccontextmanager

# Importar scheduler y jobs
from app.shared.scheduler import get_scheduler
from app.shared.scheduler.jobs import register_cache_cleanup_job

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manejo del ciclo de vida de la aplicación.
    """
    # Startup: Iniciar scheduler
    scheduler = get_scheduler()
    
    # Registrar jobs
    register_cache_cleanup_job(scheduler)
    
    # Iniciar scheduler
    scheduler.start()
    logger.info("Scheduler iniciado con jobs programados")
    
    yield
    
    # Shutdown: Detener scheduler
    scheduler.shutdown(wait=True)
    logger.info("Scheduler detenido")

# Crear aplicación con lifespan
app = FastAPI(
    title="DoxAI API",
    version="1.0.0",
    lifespan=lifespan  # <--- Agregar aquí
)

# ... resto del código
```

### Alternativa: Eventos Startup/Shutdown (FastAPI < 0.109)

```python
from app.shared.scheduler import get_scheduler
from app.shared.scheduler.jobs import register_cache_cleanup_job

@app.on_event("startup")
async def startup_event():
    """Ejecuta al iniciar la aplicación."""
    scheduler = get_scheduler()
    register_cache_cleanup_job(scheduler)
    scheduler.start()
    logger.info("Scheduler iniciado")

@app.on_event("shutdown")
async def shutdown_event():
    """Ejecuta al detener la aplicación."""
    scheduler = get_scheduler()
    scheduler.shutdown(wait=True)
    logger.info("Scheduler detenido")
```

## Configuración

### 3. Variables de Entorno (Opcional)

Agregar a `.env`:

```env
# Scheduler Configuration
SCHEDULER_ENABLED=true
CACHE_CLEANUP_INTERVAL_HOURS=1
SCHEDULER_TIMEZONE=UTC
```

### 4. Configurar Logging

Agregar a configuración de logging:

```python
# backend/app/shared/config.py

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "loggers": {
        "apscheduler": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        "app.shared.scheduler": {
            "level": "INFO",
            "handlers": ["console", "file"],
            "propagate": False,
        },
    },
}
```

## Verificación

### 5. Probar el Sistema

```bash
# Iniciar aplicación
cd backend
uvicorn app.main:app --reload

# Verificar logs
# Deberías ver:
# INFO - SchedulerService inicializado
# INFO - Job 'cache_cleanup_hourly' agregado: cada 1h 0m 0s
# INFO - SchedulerService iniciado
```

### 6. Endpoint de Monitoreo (Opcional)

Agregar endpoint para ver jobs activos:

```python
# backend/app/modules/admin/routes/scheduler_routes.py

from fastapi import APIRouter, Depends
from app.shared.scheduler import get_scheduler

router = APIRouter(prefix="/admin/scheduler", tags=["admin-scheduler"])

@router.get("/jobs")
async def list_scheduled_jobs():
    """Lista todos los jobs programados."""
    scheduler = get_scheduler()
    return {
        "is_running": scheduler.is_running,
        "jobs": scheduler.get_jobs()
    }

@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Obtiene estado de un job específico."""
    scheduler = get_scheduler()
    status = scheduler.get_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return status
```

## Monitoreo en Producción

### 7. Logs de Ejecución

Los jobs registran automáticamente sus ejecuciones:

```
2025-11-05 14:00:00 INFO - Iniciando limpieza programada de caché de metadatos
2025-11-05 14:00:00 INFO - Limpieza completada: 150 entradas eliminadas, ~300KB liberados, duración: 45.67ms, hit rate: 78.5%
```

### 8. Alertas Automáticas

El sistema genera alertas cuando:
- Caché > 90% de capacidad
- Hit rate < 60%
- Errores durante ejecución

```
2025-11-05 14:00:00 WARNING - Caché al 95.0% de capacidad (1900/2000). Considere aumentar max_size o reducir TTL.
```

### 9. Métricas para Prometheus (Opcional)

```python
from prometheus_client import Counter, Histogram

cache_cleanup_counter = Counter(
    'cache_cleanup_runs_total',
    'Total de ejecuciones de limpieza de caché'
)

cache_entries_removed = Counter(
    'cache_entries_removed_total',
    'Total de entradas eliminadas del caché'
)

cache_cleanup_duration = Histogram(
    'cache_cleanup_duration_seconds',
    'Duración de limpieza de caché'
)
```

## Troubleshooting

### Problema: Jobs no se ejecutan

**Solución**:
1. Verificar que el scheduler está iniciado: `scheduler.is_running`
2. Revisar logs de APScheduler
3. Verificar que el job está registrado: `scheduler.get_jobs()`

### Problema: Múltiples ejecuciones simultáneas

**Solución**:
- Configurado automáticamente con `max_instances=1`
- Verificar en logs si hay warnings de "missed executions"

### Problema: Timezone incorrecto

**Solución**:
- Scheduler configurado con `timezone='UTC'`
- Todos los timestamps en UTC
- Convertir a timezone local si es necesario

## Testing

### 10. Ejecutar Tests

```bash
pytest backend/tests/shared/scheduler/test_cache_cleanup_job.py -vv
```

**Resultado esperado**:
```
test_cleanup_expired_cache_success PASSED
test_cleanup_expired_cache_no_entries PASSED
test_cleanup_expired_cache_handles_errors PASSED
test_cleanup_logs_warning_when_cache_full PASSED
test_cleanup_logs_warning_when_low_hit_rate PASSED
test_register_cache_cleanup_job PASSED
test_cleanup_calculates_duration PASSED

========== 7 passed ==========
```

## Próximos Pasos

1. ✅ Instalar APScheduler: `pip install apscheduler`
2. ✅ Integrar con FastAPI (modificar `main.py`)
3. ✅ Verificar logs de inicio
4. ✅ Ejecutar tests
5. ✅ Monitorear primera ejecución (después de 1 hora)
6. 🔄 Opcional: Agregar endpoint de monitoreo
7. 🔄 Opcional: Integrar con Prometheus

---

**Fecha de creación**: 2025-11-05  
**Autor**: DoxAI Backend Team
