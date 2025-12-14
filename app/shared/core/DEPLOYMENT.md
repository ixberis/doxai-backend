# Guía de Despliegue - Core Warm-up System

## 📋 Checklist Pre-Despliegue (últimos 10 minutos)

### ✅ 1. Variables de Entorno

Verificar que todas las variables estén configuradas:

```bash
# Warm-up básico
WARMUP_ENABLE=true
WARMUP_TIMEOUT_SEC=120
WARMUP_SILENCE_PDFMINER=true

# Precargas de modelos (según necesidad)
WARMUP_PRELOAD_FAST=true
WARMUP_PRELOAD_HIRES=false  # opcional, más lento
WARMUP_PRELOAD_TABLE_MODEL=false  # opcional

# Cliente HTTP
WARMUP_HTTP_CLIENT=true
WARMUP_HTTP_HEALTH_CHECK=true
WARMUP_HTTP_HEALTH_URL=https://api.yourdomain.com/health
WARMUP_HTTP_HEALTH_TIMEOUT_SEC=10
WARMUP_HTTP_HEALTH_WARN_MS=500

# Configuración HTTP (opcional)
HTTP_PROXY=http://proxy.corp.com:8080  # si aplica
NO_PROXY=localhost,127.0.0.1,.internal  # si aplica
HTTP_BASE_URL=https://api.yourdomain.com
HTTP_EXTRA_HEADERS={"X-Internal-Token":"secret123"}

# Logging
LOG_EMOJI=false  # recomendado en producción
LOG_LEVEL=INFO
```

### ✅ 2. Dependencias Críticas

**REQUISITO MÍNIMO:** `httpx>=0.26.0`

El sistema de reintentos HTTP requiere httpx 0.26+ para soporte de `AsyncHTTPTransport(retries=N)`.

Verificar en `requirements.txt` o `pyproject.toml`:
```txt
httpx>=0.26.0,<1.0.0
```

Otras dependencias importantes:
```txt
unstructured[pdf]>=0.15.0  # para partition_pdf
pdfminer.six>=20221105
pymupdf>=1.24.0  # fitz
pytesseract>=0.3.10  # OCR (opcional)
```

**⚠️ Lockfile:** Asegúrate de tener un lockfile actualizado (`requirements.lock`, `poetry.lock`, `pdm.lock`) para builds reproducibles.

### ✅ 3. Asset de Warm-up

**Ubicación requerida:** `app/shared/assets/warmup/warmup_es_min.pdf`

Si `WARMUP_PRELOAD_FAST=true`, este archivo **debe existir** o el warm-up marcará `fast_ok=False`.

**Recomendaciones:**
- Incluir en control de versiones (Git LFS si es >1MB)
- Añadir check en pipeline CI:
  ```bash
  test -f app/shared/assets/warmup/warmup_es_min.pdf || exit 1
  ```
- Si no puedes incluirlo, desactiva `WARMUP_PRELOAD_FAST=false`

### ✅ 4. Health-check URL

Validar que la URL configurada sea accesible desde el entorno de despliegue:

```bash
# Test manual
curl -I https://api.yourdomain.com/health
# Debe retornar 200-299 en < 500ms idealmente
```

**Errores comunes:**
- URL inválida o vacía → el sistema lo marca como `warning` y continúa
- Timeout muy corto → aumenta `WARMUP_HTTP_HEALTH_TIMEOUT_SEC`
- Latencia alta → revisa `WARMUP_HTTP_HEALTH_WARN_MS` (default: 500ms)

### ✅ 5. Observabilidad

Asegúrate de tener dashboards/alertas para:

**Métricas críticas:**
```python
warmup_status.is_ready          # Boolean: sistema listo
warmup_status.duration_sec      # Float: tiempo de warm-up
warmup_status.fast_ok           # Boolean: precarga fast OK
warmup_status.http_client_ok    # Boolean: cliente HTTP OK
warmup_status.http_health_ok    # Boolean: health-check OK
warmup_status.http_health_latency_ms  # Float: latencia del ping
warmup_status.errors            # List[str]: errores duros
warmup_status.warnings          # List[str]: avisos no bloqueantes
```

**Ejemplo de endpoint de status:**
```python
from app.shared.core import get_warmup_status

@app.get("/status/warmup")
async def warmup_status_endpoint():
    status = get_warmup_status()
    return {
        "ready": status.is_ready,
        "duration_sec": status.duration_sec,
        "checks": {
            "fast": status.fast_ok,
            "http_client": status.http_client_ok,
            "http_health": status.http_health_ok,
            "tesseract": status.tesseract_ok,
            "ghostscript": status.ghostscript_ok,
            "poppler": status.poppler_ok,
        },
        "latency_ms": status.http_health_latency_ms,
        "errors": status.errors,
        "warnings": status.warnings,
    }
```

**Alertas recomendadas:**
- `duration_sec > 60s` → warm-up lento, revisar logs
- `is_ready == False` → sistema no listo, bloquear tráfico
- `len(errors) > 0` → errores críticos, investigar
- `http_health_latency_ms > 1000ms` → degradación de red

### ✅ 6. Integración con FastAPI Lifespan

Para evitar arranques fríos, ejecuta `run_warmup_once()` en el evento de startup:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.shared.core import run_warmup_once

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ejecutar warm-up una sola vez
    await run_warmup_once()
    yield
    # Shutdown: cerrar recursos si es necesario
    # (httpx client se cierra automáticamente)

app = FastAPI(lifespan=lifespan)
```

**Alternativa con eventos legacy:**
```python
@app.on_event("startup")
async def startup_event():
    await run_warmup_once()
```

---

## 🚀 Estrategia de Despliegue Recomendada

### Canary Deployment (5-10% tráfico)

1. **Desplegar canary con warm-up habilitado**
   ```bash
   # En tu CD pipeline
   kubectl set image deployment/api-canary api=api:v2.0.0
   kubectl rollout status deployment/api-canary
   ```

2. **Observar métricas durante 15 minutos**
   - `is_ready`: debe ser `true` en todos los pods
   - `duration_sec`: < 30s idealmente (depende de precargas)
   - `errors`: debe estar vacío
   - `http_health_latency_ms`: < 500ms
   - Logs: sin errores de warm-up ni precarga

3. **Si todo verde → promover al 100%**
   ```bash
   kubectl set image deployment/api-production api=api:v2.0.0
   kubectl rollout status deployment/api-production
   ```

4. **Si hay errores → rollback inmediato**
   ```bash
   kubectl rollout undo deployment/api-canary
   # Investigar logs del pod que falló
   kubectl logs <pod-id> | grep -i "warm-up\|error"
   ```

### Blue-Green Deployment

1. **Desplegar stack "green" completo**
   ```bash
   kubectl apply -f k8s/green/
   ```

2. **Health-check del stack green**
   ```bash
   curl https://green.api.yourdomain.com/status/warmup
   # Validar is_ready=true, errors=[]
   ```

3. **Switch de tráfico (DNS o load balancer)**
   ```bash
   # Ejemplo con AWS ALB target groups
   aws elbv2 modify-listener --listener-arn $LISTENER_ARN \
     --default-actions TargetGroupArn=$GREEN_TG_ARN
   ```

4. **Monitorear durante 10 minutos**
   - Errores de aplicación
   - Latencias P95/P99
   - Throughput

5. **Si OK → eliminar stack blue**
   ```bash
   kubectl delete -f k8s/blue/
   ```

---

## ⚠️ Riesgos Residuales y Mitigación

### 1. Asset de warm-up ausente

**Riesgo:** Si `WARMUP_PRELOAD_FAST=true` pero el PDF no existe, `fast_ok=False` y logs de error.

**Mitigación:**
- ✅ Check en CI/CD pipeline (ver sección 3)
- ✅ Alerta en despliegue si `errors` contiene "Asset de warm-up no encontrado"
- ✅ Opción A: incluir asset en imagen Docker
- ✅ Opción B: descargar desde S3/blob storage en runtime
- ✅ Opción C: desactivar `WARMUP_PRELOAD_FAST=false` si no es crítico

### 2. Versionado de httpx insuficiente

**Riesgo:** Si httpx < 0.26, el parámetro `retries` en `AsyncHTTPTransport` no existe → excepción en startup.

**Mitigación:**
- ✅ Pin explícito en `requirements.txt`: `httpx>=0.26.0,<1.0.0`
- ✅ Lockfile actualizado (`pip freeze > requirements.lock`)
- ✅ Test de integración que valide la versión:
  ```python
  import httpx
  assert tuple(map(int, httpx.__version__.split('.'))) >= (0, 26, 0)
  ```

### 3. Cambios futuros en Unstructured

**Riesgo:** Actualizaciones de `unstructured` pueden cambiar `env_config` o APIs internas.

**Mitigación:**
- ✅ Pin version range: `unstructured[pdf]>=0.15.0,<0.16.0`
- ✅ Revisar release notes antes de upgrades
- ✅ Tests de regresión que validen `partition_pdf()` con `fast` y `hi_res`
- ✅ Código defensivo: try/except en preloads con fallback graceful

### 4. CORS con credenciales

**Riesgo:** Si usas `allow_credentials=True` en middleware CORS, no puedes usar `origins=["*"]`.

**Mitigación:**
- ✅ Lista explícita de orígenes permitidos en settings:
  ```python
  # En settings
  cors_allowed_origins: list[str] = ["https://app.yourdomain.com"]
  
  # En middleware
  app.add_middleware(
      CORSMiddleware,
      allow_origins=settings.cors_allowed_origins,
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
  )
  ```
- ✅ Variable de entorno: `CORS_ALLOWED_ORIGINS=https://app1.com,https://app2.com`

### 5. Proxies corporativos y SSL

**Riesgo:** Proxies con SSL inspection pueden causar errores `SSLError` o `CertificateError`.

**Mitigación:**
- ✅ Configurar `NO_PROXY` para endpoints internos
- ✅ Si el proxy tiene CA custom, añadir cert al truststore:
  ```bash
  export SSL_CERT_FILE=/etc/ssl/certs/corporate-ca.crt
  ```
- ✅ En casos extremos (dev/staging solamente): `verify=False` (NO en prod)

---

## 📊 Checklist Go-Live Final

### Pre-lanzamiento (T-30 min)

- [ ] Pipeline CI pasó todos los tests
- [ ] Lockfile de dependencias actualizado
- [ ] Asset `warmup_es_min.pdf` presente en imagen/repo
- [ ] Variables de entorno revisadas (ver sección 1)
- [ ] Health-check URL accesible desde pods (`curl` manual exitoso)
- [ ] Dashboards de observabilidad listos
- [ ] Plan de rollback documentado y comunicado

### Durante canary (T+0 a T+15 min)

- [ ] Pods arrancan sin errores de warm-up
- [ ] `is_ready=true` en todos los pods canary
- [ ] `duration_sec` < 60s (ideal < 30s)
- [ ] `errors=[]` en todos los pods
- [ ] `http_health_latency_ms` < 500ms
- [ ] Sin degradación de latencias P95 vs baseline
- [ ] Sin aumento de error rate 5xx

### Post-lanzamiento (T+15 a T+60 min)

- [ ] Promoción a 100% del tráfico
- [ ] Monitoreo continuo por 1 hora
- [ ] Alertas de warm-up silenciadas (no disparadas)
- [ ] Logs revisados: sin errores/warnings inesperados
- [ ] Stack anterior eliminado (si blue-green)

---

## 🔍 Troubleshooting Común

### Problema: `is_ready=False` tras despliegue

**Causas:**
1. `fast_ok=False` → asset faltante o timeout
2. `http_client_ok=False` → error creando httpx client (ej: proxy inválido)

**Solución:**
```bash
# Ver logs del pod
kubectl logs <pod-id> | grep -E "warm-up|ERROR|❌"

# Revisar status detallado
curl http://<pod-ip>:8000/status/warmup
```

### Problema: Warm-up tarda >60s

**Causas:**
1. `WARMUP_PRELOAD_HIRES=true` → modelo pesado, desactiva si no es necesario
2. `WARMUP_PRELOAD_TABLE_MODEL=true` → modelo grande, desactiva si no usas tablas
3. Red lenta en health-check → revisa conectividad

**Solución:**
- Desactiva precargas opcionales: `WARMUP_PRELOAD_HIRES=false`
- Aumenta timeout: `WARMUP_TIMEOUT_SEC=180`

### Problema: `http_health_latency_ms` muy alto (>2000ms)

**Causas:**
1. Endpoint de health remoto lento
2. Proxy intermedio agregando latencia
3. DNS lookup lento

**Solución:**
- Usa endpoint local/interno: `WARMUP_HTTP_HEALTH_URL=http://localhost:8000/ping`
- Configura `NO_PROXY` para excluir localhost
- Aumenta threshold: `WARMUP_HTTP_HEALTH_WARN_MS=2000`

### Problema: Errores de SSL/certificados

**Causas:**
1. Proxy corporativo con SSL inspection
2. Certificado expirado en endpoint externo
3. CA custom no reconocida

**Solución:**
```bash
# Instalar CA custom en imagen Docker
COPY corporate-ca.crt /usr/local/share/ca-certificates/
RUN update-ca-certificates

# O variable de entorno
ENV SSL_CERT_FILE=/etc/ssl/certs/corporate-ca.pem
```

---

## 📚 Referencias

- **Código fuente:** `backend/app/shared/core/warmup_orchestrator_cache.py`
- **Configuración:** `backend/app/shared/config/settings_*.py`
- **httpx docs:** https://www.python-httpx.org/
- **unstructured docs:** https://unstructured-io.github.io/unstructured/

---

**Última actualización:** 2025-10-24  
**Autor:** Ixchel Beristain  
**Revisión:** Equipo DevOps
