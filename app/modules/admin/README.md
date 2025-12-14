# Módulo de Administración

Endpoints administrativos para monitoreo y gestión del sistema DoxAI.

## Endpoints de Caché

### Autenticación

Todos los endpoints requieren el header `X-Admin-Key`:

```bash
X-Admin-Key: your-admin-key-here
```

La clave se configura con la variable de entorno:
```bash
ADMIN_API_KEY=your-secure-key-in-production
```

**⚠️ IMPORTANTE**: Cambiar la clave por defecto en producción.

## Endpoints Disponibles

### 1. Ver Estadísticas del Caché

```bash
GET /api/admin/cache/stats
```

**Headers:**
```
X-Admin-Key: your-admin-key
```

**Response:**
```json
{
  "size": 450,
  "max_size": 1000,
  "hits": 2500,
  "misses": 300,
  "hit_rate_percent": 89.29,
  "evictions": 50,
  "invalidations": 120,
  "total_requests": 2800
}
```

**Ejemplo curl:**
```bash
curl -X GET "http://localhost:8000/api/admin/cache/stats" \
  -H "X-Admin-Key: dev-admin-key-change-in-production"
```

**Ejemplo Python:**
```python
import requests

response = requests.get(
    "http://localhost:8000/api/admin/cache/stats",
    headers={"X-Admin-Key": "dev-admin-key-change-in-production"}
)
print(response.json())
```

---

### 2. Estado de Salud del Caché

```bash
GET /api/admin/cache/health
```

**Headers:**
```
X-Admin-Key: your-admin-key
```

**Response:**
```json
{
  "status": "healthy",
  "size": 450,
  "capacity_percent": 45.0,
  "hit_rate_percent": 89.29,
  "warnings": []
}
```

Estados posibles:
- `healthy` - Todo funciona correctamente
- `degraded` - Hit rate bajo o uso excesivo de memoria
- `critical` - Problemas graves que requieren atención

**Ejemplo curl:**
```bash
curl -X GET "http://localhost:8000/api/admin/cache/health" \
  -H "X-Admin-Key: dev-admin-key-change-in-production"
```

---

### 3. Limpiar Todo el Caché

```bash
POST /api/admin/cache/clear
```

**Headers:**
```
X-Admin-Key: your-admin-key
```

**Response:**
```json
{
  "cleared_count": 450,
  "message": "Cache cleared successfully. 450 entries removed."
}
```

**⚠️ Advertencia**: Esto causará cache misses hasta que se vuelva a llenar.

**Ejemplo curl:**
```bash
curl -X POST "http://localhost:8000/api/admin/cache/clear" \
  -H "X-Admin-Key: dev-admin-key-change-in-production"
```

---

### 4. Invalidar por Patrón

```bash
POST /api/admin/cache/invalidate
```

**Headers:**
```
X-Admin-Key: your-admin-key
Content-Type: application/json
```

**Body:**
```json
{
  "pattern": "input_meta:"
}
```

**Response:**
```json
{
  "invalidated_count": 150,
  "pattern": "input_meta:",
  "message": "Invalidated 150 entries matching pattern 'input_meta:'"
}
```

**Patrones comunes:**
- `"input_meta:"` - Todos los metadatos de archivos input
- `"product_meta:"` - Todos los metadatos de archivos product
- `"input_meta:user123"` - Metadatos de input de un usuario específico

**Ejemplo curl:**
```bash
curl -X POST "http://localhost:8000/api/admin/cache/invalidate" \
  -H "X-Admin-Key: dev-admin-key-change-in-production" \
  -H "Content-Type: application/json" \
  -d '{"pattern": "input_meta:"}'
```

---

### 5. Reiniciar Estadísticas

```bash
POST /api/admin/cache/reset-stats
```

**Headers:**
```
X-Admin-Key: your-admin-key
```

**Response:**
```json
{
  "message": "Cache statistics reset successfully",
  "status": "ok"
}
```

**Ejemplo curl:**
```bash
curl -X POST "http://localhost:8000/api/admin/cache/reset-stats" \
  -H "X-Admin-Key: dev-admin-key-change-in-production"
```

---

## Monitoreo en Producción

### Dashboard de Métricas

Puedes crear un dashboard simple con estas métricas:

```python
import requests
import time

def monitor_cache(interval=60):
    """Monitor cache every 60 seconds"""
    url = "http://your-api.com/api/admin/cache/stats"
    headers = {"X-Admin-Key": "your-key"}
    
    while True:
        try:
            resp = requests.get(url, headers=headers)
            stats = resp.json()
            
            print(f"[{time.strftime('%H:%M:%S')}] Cache Stats:")
            print(f"  Size: {stats['size']}/{stats['max_size']}")
            print(f"  Hit Rate: {stats['hit_rate_percent']}%")
            print(f"  Evictions: {stats['evictions']}")
            
            # Alertas
            if stats['hit_rate_percent'] < 50:
                print("  ⚠️  WARNING: Low hit rate!")
            if stats['size'] / stats['max_size'] > 0.9:
                print("  ⚠️  WARNING: Cache almost full!")
                
        except Exception as e:
            print(f"Error: {e}")
        
        time.sleep(interval)

if __name__ == "__main__":
    monitor_cache()
```

### Alertas Recomendadas

1. **Hit Rate < 50%**: Revisar patrones de acceso o aumentar TTL
2. **Capacity > 90%**: Aumentar max_size
3. **Evictions frecuentes**: Aumentar max_size o reducir TTL
4. **Status = critical**: Investigar inmediatamente

### Integración con Prometheus

```python
from prometheus_client import Gauge
import requests

cache_size = Gauge('cache_size', 'Current cache size')
cache_hit_rate = Gauge('cache_hit_rate', 'Cache hit rate percentage')
cache_evictions = Gauge('cache_evictions', 'Total cache evictions')

def collect_cache_metrics():
    resp = requests.get(
        "http://localhost:8000/api/admin/cache/stats",
        headers={"X-Admin-Key": "your-key"}
    )
    stats = resp.json()
    
    cache_size.set(stats['size'])
    cache_hit_rate.set(stats['hit_rate_percent'])
    cache_evictions.set(stats['evictions'])
```

## Seguridad

### Proteger Endpoints en Producción

1. **Cambiar ADMIN_API_KEY**:
```bash
export ADMIN_API_KEY="$(openssl rand -hex 32)"
```

2. **Usar HTTPS**: Nunca enviar la clave en HTTP simple

3. **Rotar claves regularmente**: Cambiar la clave cada 90 días

4. **Limitar acceso por IP**: Usar firewall o nginx para restringir IPs

5. **Auditar accesos**: Los endpoints logean cada acceso

### Mejora: Autenticación JWT

Para producción seria, reemplazar la clave simple con JWT:

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
import jwt

security = HTTPBearer()

async def verify_admin_jwt(credentials: HTTPBearer = Depends(security)):
    try:
        payload = jwt.decode(
            credentials.credentials,
            key="your-secret",
            algorithms=["HS256"]
        )
        if payload.get("role") != "admin":
            raise HTTPException(status_code=403)
    except:
        raise HTTPException(status_code=401)
```

## Troubleshooting

### Error 401: Missing X-Admin-Key header

**Causa**: No se incluyó el header de autenticación

**Solución**:
```bash
curl -H "X-Admin-Key: your-key" ...
```

### Error 403: Invalid admin key

**Causa**: La clave proporcionada no coincide

**Solución**:
1. Verificar que `ADMIN_API_KEY` esté configurada
2. Usar la clave correcta en el header

### Error 500: Error retrieving cache stats

**Causa**: Problema con el caché interno

**Solución**:
1. Revisar logs del servidor
2. Reiniciar el caché si es necesario
3. Verificar que el módulo de caché esté inicializado

---

## Endpoints de Scheduler

El módulo admin también proporciona endpoints para monitorear el sistema de jobs programados.

### Ver todos los jobs

```bash
GET /api/admin/scheduler/jobs
```

**Response:**
```json
{
  "is_running": true,
  "jobs": [
    {
      "id": "cache_cleanup_hourly",
      "name": "cache_cleanup_hourly",
      "next_run": "2025-11-05T15:00:00",
      "trigger": "interval[1:00:00]"
    }
  ]
}
```

### Ver estado de un job

```bash
GET /api/admin/scheduler/jobs/{job_id}
```

### Pausar un job

```bash
POST /api/admin/scheduler/jobs/{job_id}/pause
```

### Reanudar un job

```bash
POST /api/admin/scheduler/jobs/{job_id}/resume
```

### Ejecutar job manualmente

```bash
POST /api/admin/scheduler/jobs/{job_id}/run-now
```

### Estadísticas de limpieza de caché

```bash
GET /api/admin/scheduler/stats/cache-cleanup?days=7
```

**Response:**
```json
{
  "period": {
    "start": "2025-10-29T00:00:00",
    "end": "2025-11-05T14:00:00",
    "days": 7
  },
  "summary": {
    "total_executions": 168,
    "total_entries_removed": 12500,
    "total_memory_freed_kb": 25000,
    "average_duration_ms": 45.3,
    "average_hit_rate": 78.5
  }
}
```

### Salud del scheduler

```bash
GET /api/admin/scheduler/health
```

**Response:**
```json
{
  "status": "healthy",
  "is_running": true,
  "jobs_count": 1,
  "warnings": []
}
```

**Ver documentación completa**: `backend/app/shared/scheduler/jobs/README.md`

---

## Autor

Ixchel Beristain  
Fecha: 05/11/2025
