# Guía de Optimización del Sistema de Storage

## Resumen

El sistema de storage de DoxAI ha sido optimizado con las siguientes mejoras de rendimiento:

### 🚀 Mejoras Implementadas

1. **Connection Pooling**
   - Pool de conexiones HTTP reutilizables
   - Configuración optimizada de keep-alive
   - Soporte HTTP/2 para mejor throughput
   - Límites ajustables por entorno

2. **Compresión Automática**
   - Detección inteligente de archivos comprimibles
   - Múltiples algoritmos: gzip, zlib, brotli
   - Compresión solo cuando es beneficiosa (>10% ahorro)
   - Métricas de ratio de compresión

3. **Cache Mejorado**
   - Cache L1 (memoria) para acceso ultrarrápido
   - Cache L2 (disco opcional) para mayor capacidad
   - Métricas detalladas de hit/miss rate
   - Evicción LRU inteligente
   - Compresión en cache para maximizar capacidad

## Componentes Principales

### ConnectionPool
```python
from app.shared.utils.connection_pool import get_pooled_client

# Obtener cliente HTTP con pooling
client = await get_pooled_client()
```

**Configuración:**
- `max_connections`: 100 (ajustable según carga)
- `max_keepalive_connections`: 20
- `keepalive_expiry`: 30 segundos
- HTTP/2 habilitado por defecto

### CompressionService
```python
from app.modules.files.services.storage.compression_service import get_compression_service

compressor = get_compression_service()

# Compresión inteligente (solo si vale la pena)
result = compressor.smart_compress(data, mime_type="text/plain")
print(f"Ahorro: {result.savings_percent:.1f}%")

# Descompresión
original = compressor.decompress(result.data, result.algorithm)
```

**Heurísticas:**
- No comprime archivos < 1 KB
- No comprime formatos ya comprimidos (jpeg, png, pdf, zip)
- Solo comprime si ahorro > 10%
- Tipos MIME comprimibles: text/*, application/json, etc.

### EnhancedCache
```python
from app.modules.files.services.storage import EnhancedCache

cache = EnhancedCache(
    max_entries_l1=256,
    max_size_bytes_l1=100 * 1024 * 1024,  # 100 MB
    ttl_seconds=300,
    enable_compression=True,
    enable_metrics=True,
)

# Usar cache
data = await cache.get_or_cache("key", fetcher_function)

# Ver métricas
metrics = cache.get_metrics()
print(f"Hit rate: {metrics.hit_rate*100:.1f}%")
cache.log_metrics()
```

### DownloadCache (Compatible)
```python
from app.modules.files.services.storage import DownloadCache

# Versión básica (para tests)
cache = DownloadCache(max_entries=256, ttl_seconds=300)

# Versión optimizada (automática si disponible)
cache = DownloadCache(
    max_entries=256,
    ttl_seconds=300,
    enable_compression=True,  # Habilita EnhancedCache
    enable_metrics=True,
)
```

## Métricas de Rendimiento

### CacheMetrics
```python
metrics = cache.get_metrics()
if metrics:
    print(f"Total requests: {metrics.total_requests}")
    print(f"Hit rate: {metrics.hit_rate*100:.1f}%")
    print(f"Requests/sec: {metrics.requests_per_second:.2f}")
    print(f"Bytes cached: {metrics.total_bytes_cached:,}")
    print(f"Bytes served: {metrics.total_bytes_served:,}")
```

### Estadísticas Esperadas

Con las optimizaciones:
- **Hit rate del cache**: 70-85% en producción
- **Reducción de latencia**: 50-80% en cache hits
- **Ahorro de ancho de banda**: 20-40% con compresión
- **Throughput**: 2-3x más requests/segundo

## Configuración por Entorno

### Desarrollo
```python
# Configuración ligera para tests
cache = DownloadCache(
    max_entries=128,
    ttl_seconds=60,
    enable_compression=False,  # Deshabilitado para tests rápidos
    enable_metrics=False,
)
```

### Producción
```python
# Configuración optimizada
cache = EnhancedCache(
    max_entries_l1=512,
    max_size_bytes_l1=200 * 1024 * 1024,  # 200 MB
    ttl_seconds=600,  # 10 minutos
    enable_compression=True,
    compression_algo="gzip",
    enable_metrics=True,
    disk_cache_dir=Path("/var/cache/doxai/storage"),  # L2 opcional
    max_size_bytes_l2=1024 * 1024 * 1024,  # 1 GB
)
```

## Monitoreo

### Logging Automático
Las métricas se registran automáticamente en los logs:
```
📊 Cache Metrics Summary:
  Requests: 1000 (3.33/s)
  Hit Rate: 78.5% (785 hits, 215 misses)
  Evictions: 23, Expirations: 12
  Cached: 45,231,456 bytes
  Served: 89,567,234 bytes
  Uptime: 300.0s
```

### Métricas Programáticas
```python
# Obtener métricas como diccionario
metrics_dict = cache.get_metrics().to_dict()

# Registrar en sistema de monitoreo
send_to_monitoring(metrics_dict)
```

## Migración de Código Existente

### Antes
```python
from app.modules.files.services.storage.download_cache import DownloadCache

cache = DownloadCache()
data = await cache.get_or_cache(key, fetcher)
```

### Después (compatible, con optimizaciones)
```python
from app.modules.files.services.storage import DownloadCache

# Igual API, mejoras automáticas
cache = DownloadCache(enable_compression=True, enable_metrics=True)
data = await cache.get_or_cache(key, fetcher)

# Acceso a nuevas funcionalidades
cache.log_metrics()
```

## Pruebas de Rendimiento

### Benchmark del Cache
```bash
# Ejecutar tests de performance
pytest backend/tests/modules/files/services/storage/test_cache_performance.py -v
```

### Benchmark de Compresión
```bash
# Ejecutar tests de compresión
pytest backend/tests/modules/files/services/storage/test_compression_performance.py -v
```

## Troubleshooting

### Cache no mejora rendimiento
- Verificar que `enable_compression=True`
- Aumentar `max_entries` y `max_size_bytes`
- Revisar logs para evictions frecuentes
- Considerar habilitar cache L2 en disco

### Compresión no reduce tamaño
- Verificar tipos MIME (algunos ya están comprimidos)
- Ajustar `MIN_COMPRESSION_RATIO` si es necesario
- Probar diferentes algoritmos (brotli > gzip > zlib para texto)

### Connection pool saturado
- Aumentar `max_connections` en ConnectionPool
- Revisar logs para timeouts
- Considerar escalar horizontalmente

## Referencias

- [Connection Pooling Guide](./connection_pooling.md)
- [Compression Best Practices](./compression_best_practices.md)
- [Cache Strategy](./cache_strategy.md)
- [Performance Tuning](./performance_tuning.md)

## Changelog

### v1.0 (2025-11-05)
- ✅ Connection pooling con HTTP/2
- ✅ Compresión inteligente (gzip, zlib, brotli)
- ✅ Cache multinivel (L1 memoria, L2 disco opcional)
- ✅ Sistema de métricas completo
- ✅ Compatibilidad con código existente

---

**Autor**: DoxAI Team  
**Última actualización**: 2025-11-05
