# Jobs Programados del Sistema

Este directorio contiene los jobs programados que se ejecutan periódicamente en el backend.

## Jobs Disponibles

### 1. Cache Cleanup Job

**Archivo**: `cache_cleanup_job.py`

**Descripción**: Limpia automáticamente entradas expiradas del caché de metadatos.

**Configuración**:
- **Frecuencia**: Cada hora (top of the hour)
- **Función**: `cleanup_expired_cache()`
- **Job ID**: `cache_cleanup_hourly`

**Estadísticas Registradas**:
```json
{
  "timestamp": "2025-11-05T14:00:00.123456",
  "entries_before": 1250,
  "entries_after": 1100,
  "entries_removed": 150,
  "memory_freed_kb": 300,
  "duration_ms": 45.67,
  "hit_rate": 78.5,
  "evictions": 23
}
```

**Alertas Automáticas**:
- ⚠️ Caché > 90% de capacidad
- ⚠️ Hit rate < 60%
- ⚠️ Errores durante limpieza

**Logs**:
```
INFO: Limpieza completada: 150 entradas eliminadas, ~300KB liberados, duración: 45.67ms, hit rate: 78.5%
WARNING: Caché al 95.0% de capacidad (1900/2000). Considere aumentar max_size o reducir TTL.
```

## Agregar Nuevos Jobs

### Paso 1: Crear el Job

Crear archivo en `backend/app/shared/scheduler/jobs/`:

```python
# my_custom_job.py
import logging

logger = logging.getLogger(__name__)

async def my_job_function() -> dict:
    """
    Descripción del job.
    
    Returns:
        Dict con estadísticas de ejecución
    """
    logger.info("Ejecutando my_job_function")
    
    try:
        # Lógica del job aquí
        result = perform_task()
        
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'status': 'success',
            'items_processed': result
        }
    except Exception as e:
        logger.error(f"Error en my_job_function: {e}", exc_info=True)
        return {'status': 'error', 'error': str(e)}


def register_my_job(scheduler) -> str:
    """Registra el job en el scheduler."""
    return scheduler.add_interval_job(
        func=my_job_function,
        job_id="my_custom_job",
        hours=2  # Cada 2 horas
    )
```

### Paso 2: Exportar en __init__.py

```python
# __init__.py
from .my_custom_job import my_job_function, register_my_job

__all__ = [
    "cleanup_expired_cache",
    "register_cache_cleanup_job",
    "my_job_function",  # Nuevo
    "register_my_job",  # Nuevo
]
```

### Paso 3: Registrar en main.py

```python
# main.py
from app.shared.scheduler import get_scheduler
from app.shared.scheduler.jobs import register_cache_cleanup_job, register_my_job

@app.on_event("startup")
async def startup_event():
    scheduler = get_scheduler()
    register_cache_cleanup_job(scheduler)
    register_my_job(scheduler)  # Nuevo
    scheduler.start()
```

## Tipos de Triggers

### Interval Trigger (Intervalos Regulares)

```python
scheduler.add_interval_job(
    func=my_function,
    job_id="interval_job",
    hours=1,      # Cada hora
    minutes=30,   # Cada 30 minutos
    seconds=15    # Cada 15 segundos
)
```

### Cron Trigger (Expresiones Cron)

```python
# Ejecutar a las 3:00 AM todos los días
scheduler.add_cron_job(
    func=my_function,
    job_id="cron_job",
    hour="3",
    minute="0"
)

# Expresión cron completa
scheduler.add_cron_job(
    func=my_function,
    job_id="cron_job_full",
    cron_expression="0 3 * * *"  # Min Hora Día Mes DiaSemana
)
```

## Gestión de Jobs

### Listar Jobs Activos

```python
from app.shared.scheduler import get_scheduler

scheduler = get_scheduler()
jobs = scheduler.get_jobs()

for job in jobs:
    print(f"Job: {job['id']}, Next Run: {job['next_run']}")
```

### Obtener Estado de un Job

```python
status = scheduler.get_job_status("cache_cleanup_hourly")
print(f"Next run: {status['next_run']}")
```

### Eliminar Job

```python
scheduler.remove_job("my_custom_job")
```

### Detener Scheduler

```python
scheduler.shutdown(wait=True)  # Esperar a que terminen jobs
```

## Monitoreo y Logging

### Configurar Nivel de Log

```python
import logging

logging.getLogger('apscheduler').setLevel(logging.INFO)
```

### Ver Logs de Ejecución

Los logs se escriben automáticamente con el formato:

```
INFO - Iniciando limpieza programada de caché de metadatos
INFO - Limpieza completada: 150 entradas eliminadas, ~300KB liberados
WARNING - Caché al 95.0% de capacidad (1900/2000)
ERROR - Error durante limpieza de caché: ConnectionError
```

## Buenas Prácticas

1. **Idempotencia**: Los jobs deben ser idempotentes (ejecutarse múltiples veces sin efectos secundarios)
2. **Timeout**: Implementar timeout para jobs de larga duración
3. **Error Handling**: Capturar excepciones y registrar errores
4. **Logging**: Registrar inicio, fin y estadísticas
5. **Recursos**: Liberar recursos correctamente (conexiones DB, archivos)
6. **Testing**: Crear tests unitarios para cada job

## Testing

```python
# test_cache_cleanup_job.py
import pytest
from app.shared.scheduler.jobs import cleanup_expired_cache

@pytest.mark.asyncio
async def test_cleanup_expired_cache():
    stats = await cleanup_expired_cache()
    
    assert 'timestamp' in stats
    assert 'entries_removed' in stats
    assert stats['entries_removed'] >= 0
```

## Troubleshooting

### Job no se ejecuta

1. Verificar que el scheduler está iniciado: `scheduler.is_running`
2. Revisar logs de APScheduler
3. Verificar expresión cron/intervalo

### Ejecuciones duplicadas

- Asegurarse de usar `replace_existing=True`
- Verificar `max_instances=1` en job_defaults

### Jobs lentos

- Implementar logging de duración
- Considerar ejecutar en thread pool separado
- Optimizar lógica del job

---

**Fecha de creación**: 2025-11-05  
**Última actualización**: 2025-11-05
