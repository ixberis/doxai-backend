# Sistema de Métricas y Monitoreo de Pagos

Sistema completo de monitoreo en tiempo real para endpoints de pagos, diseñado para capturar latencia, tasas de error y tasas de conversión por proveedor.

## Características

### 📊 Métricas de Endpoints
- **Latencia**: Percentiles P50, P95, P99 y promedio
- **Tasa de error**: Porcentaje de requests fallidos
- **Errores por tipo**: Agrupación de errores por categoría
- **Requests totales**: Contador de llamadas por endpoint

### 💳 Métricas de Conversión
- **Por proveedor**: Stripe, PayPal, etc.
- **Estados**: Exitosos, fallidos, pendientes, cancelados
- **Tasa de conversión**: % de pagos exitosos
- **Tasa de fallo**: % de pagos fallidos

### 🏥 Health Check
- **Estado general**: healthy, warning, critical
- **Alertas automáticas**: Basadas en umbrales configurables
- **Resumen del sistema**: Uptime, totales, métricas agregadas

## Arquitectura

```
monitoring/
├── __init__.py                # Exportaciones públicas
├── metrics_collector.py       # Recolector principal (Singleton)
├── metrics_storage.py         # Almacenamiento en memoria con agregación
├── decorators.py              # Decorators para captura automática
├── schemas.py                 # Schemas Pydantic de respuestas
└── README.md                  # Esta documentación
```

## Uso

### 1. Decorators en Endpoints

#### Tracking de Latencia y Errores

```python
from app.modules.payments.monitoring.decorators import track_endpoint_metrics

@router.post("/checkout")
@track_endpoint_metrics("POST /payments/checkout")
async def checkout_endpoint(payload: CheckoutRequest, ...):
    # Tu lógica aquí
    return result
```

#### Tracking de Conversiones de Pago

```python
from app.modules.payments.monitoring.decorators import (
    track_endpoint_metrics,
    track_payment_conversion,
)

@router.post("/checkout")
@track_endpoint_metrics("POST /payments/checkout")
@track_payment_conversion(provider_param="provider")
async def checkout_endpoint(provider: str, payload: CheckoutRequest, ...):
    # El decorator registra automáticamente el intento y resultado
    return {"status": "paid", "provider": provider, ...}
```

### 2. Tracking Manual

Para casos especiales donde necesitas control total:

```python
from app.modules.payments.monitoring import get_metrics_collector

# Obtener el collector
collector = get_metrics_collector()

# Registrar llamada a endpoint
collector.record_endpoint_call(
    endpoint="POST /payments/checkout",
    latency_ms=125.5,
    status_code=200,
    error=None,  # o "ValidationError", "HTTPException", etc.
)

# Registrar intento de pago
collector.record_payment_attempt(
    provider="stripe",
    status="paid",  # o "failed", "pending", "cancelled"
    amount_cents=19900,
)
```

### 3. Consultar Métricas

#### Vía API (Endpoints Administrativos)

```bash
# Resumen general
GET /payments/metrics/summary

# Métricas de endpoints (última hora)
GET /payments/metrics/endpoints?hours=1

# Métricas de conversión por proveedor
GET /payments/metrics/conversions?provider=stripe&hours=24

# Estado de salud con alertas
GET /payments/metrics/health

# Snapshot completo
GET /payments/metrics/snapshot?hours=6
```

#### Vía Código

```python
from app.modules.payments.monitoring import get_metrics_collector

collector = get_metrics_collector()

# Métricas de endpoints
endpoint_metrics = collector.get_endpoint_metrics(
    endpoint="POST /payments/checkout",  # Opcional: filtrar por endpoint
    hours=1,  # Última hora
)
# Resultado:
# {
#     "POST /payments/checkout": {
#         "total_requests": 150,
#         "total_errors": 5,
#         "error_rate": 3.33,
#         "latency": {"p50": 120, "p95": 450, "p99": 890, "avg": 180},
#         "errors_by_type": {"ValidationError": 3, "HTTP_500": 2}
#     }
# }

# Conversiones por proveedor
conversions = collector.get_provider_conversions(
    provider="stripe",  # Opcional
    hours=24,
)
# Resultado:
# {
#     "stripe": {
#         "total_attempts": 100,
#         "successful": 85,
#         "failed": 10,
#         "pending": 3,
#         "cancelled": 2,
#         "conversion_rate": 85.0,
#         "failure_rate": 10.0
#     }
# }

# Resumen general
summary = collector.get_summary()

# Estado de salud
health = collector.get_health_status()
```

## Ventanas Temporales

El sistema agrega métricas en ventanas de tiempo:

- **Minutal**: Agregación por minuto (default para storage)
- **Por hora**: Consultas típicas de 1h, 6h, 12h
- **Por día**: Retención hasta 24h por defecto

## Alertas Automáticas

El sistema genera alertas basadas en:

| Métrica | Umbral Warning | Umbral Critical |
|---------|---------------|-----------------|
| Tasa de error general | > 5% | > 10% |
| Tasa de conversión | < 70% | N/A |
| Latencia P95 | > 3s | N/A |
| Tasa de fallo por proveedor | N/A | > 20% |

## Configuración

### Retención de Datos

Por defecto, las métricas se mantienen en memoria por 24 horas:

```python
from app.modules.payments.monitoring import MetricsCollector

# Personalizar retención
collector = MetricsCollector(retention_hours=48)
```

### Límites de Buckets

Cada bucket de latencias mantiene las últimas 1000 mediciones para cálculo de percentiles.

## Ejemplo Completo

```python
# backend/app/modules/payments/routes/my_endpoint.py

from fastapi import APIRouter, Depends
from app.modules.payments.monitoring.decorators import (
    track_endpoint_metrics,
    track_payment_conversion,
)

router = APIRouter(prefix="/payments", tags=["payments"])

@router.post("/process-payment")
@track_endpoint_metrics("POST /payments/process-payment")
@track_payment_conversion(provider_param="provider")
async def process_payment(
    provider: str,
    amount: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Los decorators capturarán automáticamente:
    - Latencia de la función
    - Errores y excepciones
    - Status code de respuesta
    - Intento de conversión con el proveedor
    """
    
    # Tu lógica de negocio
    result = await create_payment_with_provider(provider, amount)
    
    # Asegúrate de retornar el status en la respuesta
    return {
        "payment_id": result.id,
        "status": result.status,  # "paid", "failed", etc.
        "provider": provider,
    }
```

## Endpoints Administrativos

Todos los endpoints de métricas requieren permisos de administrador:

### GET /payments/metrics/summary
Resumen general del sistema.

**Response:**
```json
{
  "success": true,
  "data": {
    "uptime_seconds": 86400,
    "uptime_hours": 24.0,
    "total_endpoints_tracked": 8,
    "total_providers_tracked": 2,
    "last_hour": {
      "total_requests": 1250,
      "total_errors": 42,
      "overall_error_rate": 3.36,
      "total_payment_attempts": 315,
      "total_successful_payments": 268,
      "overall_conversion_rate": 85.08
    }
  }
}
```

### GET /payments/metrics/endpoints
Métricas detalladas por endpoint.

**Query Params:**
- `endpoint` (opcional): Filtrar por endpoint específico
- `hours` (1-24): Ventana de tiempo

**Response:**
```json
{
  "success": true,
  "time_window_hours": 1,
  "total_endpoints": 5,
  "data": [
    {
      "endpoint": "POST /payments/checkout",
      "total_requests": 150,
      "total_errors": 5,
      "error_rate": 3.33,
      "latency": {
        "p50": 120.5,
        "p95": 450.2,
        "p99": 890.8,
        "avg": 180.3
      },
      "errors_by_type": {
        "ValidationError": 3,
        "HTTP_500_ServerError": 2
      }
    }
  ]
}
```

### GET /payments/metrics/conversions
Tasas de conversión por proveedor.

**Query Params:**
- `provider` (opcional): Filtrar por proveedor
- `hours` (1-24): Ventana de tiempo

**Response:**
```json
{
  "success": true,
  "time_window_hours": 24,
  "total_providers": 2,
  "data": [
    {
      "provider": "stripe",
      "total_attempts": 180,
      "successful": 152,
      "failed": 18,
      "pending": 8,
      "cancelled": 2,
      "conversion_rate": 84.44,
      "failure_rate": 10.0
    }
  ]
}
```

### GET /payments/metrics/health
Estado de salud con alertas.

**Response:**
```json
{
  "success": true,
  "data": {
    "status": "warning",
    "timestamp": "2025-11-06T10:30:00Z",
    "alerts": [
      {
        "level": "warning",
        "message": "Tasa de error elevada: 6.5%"
      }
    ],
    "metrics_summary": { /* ... */ }
  }
}
```

## Performance

- **Storage**: En memoria con thread-safety
- **Overhead**: ~1-2ms por request decorado
- **Límites**: 1000 latencias por bucket, cleanup automático cada 24h
- **Concurrencia**: Thread-safe usando `threading.Lock`

## Próximas Mejoras

- [ ] Persistencia opcional en base de datos
- [ ] Exportación a Prometheus/Grafana
- [ ] Webhooks para alertas críticas
- [ ] Dashboard visual integrado
- [ ] Métricas de monto transaccionado
- [ ] Comparación temporal (día vs día, semana vs semana)

## Troubleshooting

### Las métricas no se registran

Verifica que:
1. Los decorators están aplicados correctamente
2. El collector se inicializa al arrancar la app
3. Los endpoints retornan el formato esperado

### Memoria creciendo mucho

Ajusta el `retention_hours` o implementa cleanup más agresivo:

```python
collector = MetricsCollector(retention_hours=12)
```

### Latencias incorrectas

Los decorators miden el tiempo total de ejecución, incluyendo:
- Lógica de negocio
- Llamadas a DB
- Llamadas externas (proveedores)

Es el comportamiento esperado para end-to-end latency.

---

**Autor**: Ixchel Beristáin  
**Fecha**: 06/11/2025  
**Módulo**: DoxAI Payments
