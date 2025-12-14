# API de Monitoreo del Scheduler

Documentación completa de los endpoints de administración del scheduler.

## Autenticación

Todos los endpoints requieren autenticación con API key:

```bash
X-Admin-Key: your-admin-key-here
```

**Configuración** (en `.env`):
```env
ADMIN_API_KEY=your-secure-admin-key-123
```

## Endpoints Disponibles

### 1. Listar Jobs Activos

**GET** `/api/admin/scheduler/jobs`

Lista todos los jobs programados y su estado.

**Headers:**
```
X-Admin-Key: your-admin-key
```

**Response 200:**
```json
{
  "is_running": true,
  "jobs": [
    {
      "id": "cache_cleanup_hourly",
      "name": "cache_cleanup_hourly",
      "next_run": "2025-11-05T15:00:00.123456",
      "trigger": "interval[1:00:00]"
    }
  ]
}
```

**Ejemplo curl:**
```bash
curl -X GET "http://localhost:8000/api/admin/scheduler/jobs" \
  -H "X-Admin-Key: your-admin-key"
```

**Ejemplo Python:**
```python
import requests

response = requests.get(
    "http://localhost:8000/api/admin/scheduler/jobs",
    headers={"X-Admin-Key": "your-admin-key"}
)
print(response.json())
```

---

### 2. Estado de Job Individual

**GET** `/api/admin/scheduler/jobs/{job_id}`

Obtiene información detallada de un job específico.

**Path Parameters:**
- `job_id` (string): ID del job (ej: `cache_cleanup_hourly`)

**Response 200:**
```json
{
  "id": "cache_cleanup_hourly",
  "name": "cache_cleanup_hourly",
  "next_run": "2025-11-05T15:00:00.123456",
  "trigger": "interval[1:00:00]",
  "pending": false
}
```

**Response 404:**
```json
{
  "detail": "Job 'nonexistent_job' no encontrado"
}
```

**Ejemplo:**
```bash
curl -X GET "http://localhost:8000/api/admin/scheduler/jobs/cache_cleanup_hourly" \
  -H "X-Admin-Key: your-admin-key"
```

---

### 3. Pausar Job

**POST** `/api/admin/scheduler/jobs/{job_id}/pause`

Pausa un job programado (no se ejecutará hasta que se reanude).

**Response 200:**
```json
{
  "message": "Job 'cache_cleanup_hourly' pausado",
  "job_id": "cache_cleanup_hourly",
  "status": "paused"
}
```

**Ejemplo:**
```bash
curl -X POST "http://localhost:8000/api/admin/scheduler/jobs/cache_cleanup_hourly/pause" \
  -H "X-Admin-Key: your-admin-key"
```

**Caso de uso:** Pausar temporalmente limpieza durante mantenimiento.

---

### 4. Reanudar Job

**POST** `/api/admin/scheduler/jobs/{job_id}/resume`

Reanuda un job previamente pausado.

**Response 200:**
```json
{
  "message": "Job 'cache_cleanup_hourly' reanudado",
  "job_id": "cache_cleanup_hourly",
  "status": "active"
}
```

**Ejemplo:**
```bash
curl -X POST "http://localhost:8000/api/admin/scheduler/jobs/cache_cleanup_hourly/resume" \
  -H "X-Admin-Key: your-admin-key"
```

---

### 5. Ejecutar Job Manualmente

**POST** `/api/admin/scheduler/jobs/{job_id}/run-now`

Ejecuta un job de inmediato, sin esperar a la próxima ejecución programada.

**Response 200:**
```json
{
  "message": "Job 'cache_cleanup_hourly' ejecutado manualmente",
  "job_id": "cache_cleanup_hourly",
  "timestamp": "2025-11-05T14:30:00.123456",
  "result": {
    "timestamp": "2025-11-05T14:30:00.123456",
    "entries_before": 950,
    "entries_after": 800,
    "entries_removed": 150,
    "memory_freed_kb": 300,
    "duration_ms": 45.67,
    "hit_rate": 78.5
  }
}
```

**Ejemplo:**
```bash
curl -X POST "http://localhost:8000/api/admin/scheduler/jobs/cache_cleanup_hourly/run-now" \
  -H "X-Admin-Key: your-admin-key"
```

**Caso de uso:** Forzar limpieza inmediata cuando el caché está muy lleno.

---

### 6. Estadísticas de Limpieza

**GET** `/api/admin/scheduler/stats/cache-cleanup`

Obtiene estadísticas históricas de ejecuciones de limpieza de caché.

**Query Parameters:**
- `days` (int, optional): Días de historial (default: 7, max: 30)

**Response 200:**
```json
{
  "period": {
    "start": "2025-10-29T00:00:00.000000",
    "end": "2025-11-05T14:00:00.000000",
    "days": 7
  },
  "summary": {
    "total_executions": 168,
    "total_entries_removed": 12500,
    "total_memory_freed_kb": 25000,
    "average_duration_ms": 45.3,
    "average_hit_rate": 78.5,
    "current_cache_size": 800,
    "current_hit_rate": 80.0
  },
  "history": [
    {
      "timestamp": "2025-11-05T14:00:00.000000",
      "entries_removed": 150,
      "memory_freed_kb": 300,
      "duration_ms": 45.67,
      "hit_rate": 78.5
    }
  ],
  "note": "Historial simulado. En producción, implementar persistencia en BD."
}
```

**Ejemplo:**
```bash
# Últimos 7 días (default)
curl -X GET "http://localhost:8000/api/admin/scheduler/stats/cache-cleanup" \
  -H "X-Admin-Key: your-admin-key"

# Últimos 30 días
curl -X GET "http://localhost:8000/api/admin/scheduler/stats/cache-cleanup?days=30" \
  -H "X-Admin-Key: your-admin-key"
```

**Métricas incluidas:**
- **total_executions**: Número de veces que se ejecutó la limpieza
- **total_entries_removed**: Total de entradas eliminadas
- **total_memory_freed_kb**: Memoria total liberada (aproximada)
- **average_duration_ms**: Duración promedio de limpieza
- **average_hit_rate**: Hit rate promedio del caché
- **current_cache_size**: Tamaño actual del caché
- **current_hit_rate**: Hit rate actual

---

### 7. Salud del Scheduler

**GET** `/api/admin/scheduler/health`

Verifica el estado de salud del scheduler y jobs programados.

**Response 200:**
```json
{
  "status": "healthy",
  "is_running": true,
  "jobs_count": 1,
  "warnings": []
}
```

**Estados posibles:**
- `healthy`: Todo funciona correctamente
- `degraded`: Problemas menores (ej: sin jobs registrados)
- `unhealthy`: Problemas críticos (ej: scheduler detenido)

**Response con warnings:**
```json
{
  "status": "degraded",
  "is_running": true,
  "jobs_count": 0,
  "warnings": [
    "No hay jobs registrados"
  ]
}
```

**Response unhealthy:**
```json
{
  "status": "unhealthy",
  "is_running": false,
  "jobs_count": 0,
  "warnings": [
    "Scheduler no está activo"
  ]
}
```

**Ejemplo:**
```bash
curl -X GET "http://localhost:8000/api/admin/scheduler/health" \
  -H "X-Admin-Key: your-admin-key"
```

---

## Scripts de Monitoreo

### Dashboard Simple (Python)

```python
#!/usr/bin/env python3
"""
Dashboard simple de monitoreo del scheduler.
"""

import requests
import time
from datetime import datetime

API_URL = "http://localhost:8000/api/admin/scheduler"
ADMIN_KEY = "your-admin-key"

def get_headers():
    return {"X-Admin-Key": ADMIN_KEY}

def check_health():
    """Verifica salud del scheduler."""
    resp = requests.get(f"{API_URL}/health", headers=get_headers())
    return resp.json()

def get_jobs():
    """Obtiene lista de jobs."""
    resp = requests.get(f"{API_URL}/jobs", headers=get_headers())
    return resp.json()

def get_stats(days=7):
    """Obtiene estadísticas de limpieza."""
    resp = requests.get(
        f"{API_URL}/stats/cache-cleanup?days={days}",
        headers=get_headers()
    )
    return resp.json()

def print_dashboard():
    """Imprime dashboard en consola."""
    print(f"\n{'='*60}")
    print(f"Scheduler Dashboard - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    # Salud
    health = check_health()
    status_emoji = {
        "healthy": "✅",
        "degraded": "⚠️",
        "unhealthy": "❌"
    }
    print(f"Estado: {status_emoji[health['status']]} {health['status'].upper()}")
    print(f"Scheduler activo: {'Sí' if health['is_running'] else 'No'}")
    print(f"Jobs registrados: {health['jobs_count']}")
    
    if health['warnings']:
        print("\n⚠️  Advertencias:")
        for w in health['warnings']:
            print(f"  - {w}")
    
    # Jobs
    jobs = get_jobs()
    print(f"\n📋 Jobs Activos:")
    for job in jobs['jobs']:
        print(f"  • {job['id']}")
        print(f"    Próxima ejecución: {job['next_run']}")
    
    # Estadísticas
    stats = get_stats(days=1)
    summary = stats['summary']
    print(f"\n📊 Estadísticas (últimas 24h):")
    print(f"  Ejecuciones: {summary['total_executions']}")
    print(f"  Entradas eliminadas: {summary['total_entries_removed']}")
    print(f"  Memoria liberada: {summary['total_memory_freed_kb']} KB")
    print(f"  Hit rate promedio: {summary['average_hit_rate']:.1f}%")
    print(f"  Duración promedio: {summary['average_duration_ms']:.2f} ms")
    
    print(f"\n💾 Estado Actual del Caché:")
    print(f"  Tamaño: {summary['current_cache_size']} entradas")
    print(f"  Hit rate: {summary['current_hit_rate']:.1f}%")

def monitor_loop(interval=60):
    """Loop de monitoreo continuo."""
    try:
        while True:
            print_dashboard()
            print(f"\n⏳ Esperando {interval}s para próxima actualización...")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n\n👋 Monitoreo detenido")

if __name__ == "__main__":
    # Ejecutar una vez
    print_dashboard()
    
    # Descomentar para monitoreo continuo
    # monitor_loop(interval=60)
```

### Alertas por Slack

```python
import requests
import os

SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL")

def send_alert(message):
    """Envía alerta a Slack."""
    requests.post(SLACK_WEBHOOK, json={"text": message})

def check_and_alert():
    """Verifica salud y envía alertas si hay problemas."""
    health = requests.get(
        "http://localhost:8000/api/admin/scheduler/health",
        headers={"X-Admin-Key": "your-key"}
    ).json()
    
    if health['status'] == 'unhealthy':
        send_alert(f"🚨 SCHEDULER CRÍTICO: {health['warnings']}")
    elif health['status'] == 'degraded':
        send_alert(f"⚠️ Scheduler degradado: {health['warnings']}")
    
    # Verificar estadísticas
    stats = requests.get(
        "http://localhost:8000/api/admin/scheduler/stats/cache-cleanup?days=1",
        headers={"X-Admin-Key": "your-key"}
    ).json()
    
    hit_rate = stats['summary']['average_hit_rate']
    if hit_rate < 60:
        send_alert(f"⚠️ Hit rate bajo: {hit_rate:.1f}%")
```

## Casos de Uso

### 1. Investigar Alto Uso de Memoria

```bash
# 1. Ver estadísticas recientes
curl "http://localhost:8000/api/admin/scheduler/stats/cache-cleanup?days=1" \
  -H "X-Admin-Key: your-key"

# 2. Ver estado del caché
curl "http://localhost:8000/api/admin/cache/stats" \
  -H "X-Admin-Key: your-key"

# 3. Si es necesario, limpiar manualmente
curl -X POST "http://localhost:8000/api/admin/scheduler/jobs/cache_cleanup_hourly/run-now" \
  -H "X-Admin-Key: your-key"
```

### 2. Mantenimiento Programado

```bash
# Pausar limpieza durante deploy
curl -X POST "http://localhost:8000/api/admin/scheduler/jobs/cache_cleanup_hourly/pause" \
  -H "X-Admin-Key: your-key"

# ... realizar mantenimiento ...

# Reanudar limpieza
curl -X POST "http://localhost:8000/api/admin/scheduler/jobs/cache_cleanup_hourly/resume" \
  -H "X-Admin-Key: your-key"
```

### 3. Análisis de Rendimiento

```bash
# Obtener estadísticas de 30 días
curl "http://localhost:8000/api/admin/scheduler/stats/cache-cleanup?days=30" \
  -H "X-Admin-Key: your-key" | jq '.summary'
```

## Mejores Prácticas

1. **Monitoreo Regular**: Verificar `/health` cada 5 minutos
2. **Alertas**: Configurar alertas para `status != "healthy"`
3. **Análisis de Tendencias**: Revisar estadísticas semanalmente
4. **Documentar Pausas**: Registrar cuándo y por qué se pausan jobs
5. **Rotación de Keys**: Cambiar `ADMIN_API_KEY` trimestralmente

## Seguridad

⚠️ **IMPORTANTE**:
- Usar HTTPS en producción
- No exponer endpoints públicamente
- Rotar API key regularmente
- Limitar acceso por IP/firewall
- Auditar todos los accesos

---

**Fecha**: 2025-11-05  
**Autor**: DoxAI Backend Team
