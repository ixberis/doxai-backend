
---

```markdown
# DoxAI • Observability & Metrics (Auth)

Este directorio contiene recursos relacionados con **observabilidad** y **métricas** del sistema, con énfasis en el módulo **Auth**.

## Estructura

```

backend/app/
├─ observability/                  # Middleware ASGI + endpoint /metrics (Prometheus)
│  ├─ **init**.py
│  └─ prom.py
└─ monitoring/
└─ grafana/
└─ dashboards/
└─ auth_metrics_dashboard.json  # Dashboard base de KPIs Auth (Grafana)

````

## 1) Prometheus

### 1.1 Endpoint de scrape

La app expone el endpoint **`/metrics`** (formato Prometheus) montado por `app/observability/prom.py`.

> **Seguridad:** Mantén `/metrics` **sin autenticación** pero protegido a nivel de **ingress/red** (IP allow-list, red privada, sidecar mTLS, etc.).

### 1.2 Configuración de scrape (ejemplo)

Agrega esto a tu `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: "doxai-backend"
    scrape_interval: 15s
    metrics_path: /metrics
    static_configs:
      - targets:
          - "localhost:8000"   # o el host de tu backend
````

#### Multiproceso (gunicorn/uvicorn workers)

Si corres con múltiples workers, habilita el **modo multiproceso** de `prometheus_client`:

* Define `PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus` (o similar)
* Asegúrate de limpiar el directorio en cada arranque

```bash
export PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus
rm -rf "$PROMETHEUS_MULTIPROC_DIR" && mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
```

`app/observability/prom.py` detecta automáticamente `PROMETHEUS_MULTIPROC_DIR` y usa `CollectorRegistry` multiproceso.

## 2) Grafana

### 2.1 Importar dashboard

1. En Grafana, ve a **Dashboards → Import**.
2. Selecciona el archivo:
   `backend/app/monitoring/grafana/dashboards/auth_metrics_dashboard.json`
3. Elige tu **datasource Prometheus**.
4. Listo.

### 2.2 Métricas utilizadas (naming)

* `auth_registrations_total`
* `auth_activations_total`
* `auth_activation_conversion_ratio`
* `auth_password_resets_total{status}`
* `auth_login_attempts_total{success,reason}`
* `auth_active_sessions`
* `http_requests_total` y `http_request_latency_seconds_bucket` (middleware ASGI)

> Si cambias los nombres en los collectors, ajusta las expresiones del dashboard.

## 3) Jobs de refresco

### 3.1 En la aplicación (scheduler interno)

`app/main.py` registra un job que ejecuta cada minuto:

* `AuthMetricsService.refresh_gauges()` → sincroniza **gauges** desde BD a Prometheus (no requiere lock).

### 3.2 En la base de datos (pg_cron)

En `database/auth/07_metrics/13_auth_metrics_schedule.sql` se programa:

* `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_login_stats_30d` cada 15 min.
* `VACUUM (ANALYZE)` semanal de tablas fuente.

Asegura tener **pg_cron** habilitado y permisos para `cron.schedule`.

## 4) Desarrollo local (opcional con Docker Compose)

Ejemplo mínimo de `docker-compose.prom.yml`:

```yaml
version: "3.9"
services:
  prometheus:
    image: prom/prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
    command: ["--config.file=/etc/prometheus/prometheus.yml"]
    ports: ["9090:9090"]

  grafana:
    image: grafana/grafana
    ports: ["3000:3000"]
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana-data:/var/lib/grafana

volumes:
  grafana-data:
```

> Crea un `prometheus.yml` junto a este compose apuntando a tu backend.

## 5) Troubleshooting

* **No ves métricas en Grafana**: Verifica que Prometheus pueda **scrapear** `http://<backend>/metrics` y que el **datasource** apunte a tu Prometheus.
* **Cardinalidad alta por `path`**: Normaliza rutas a “path templates” (e.g. `/users/{id}`) antes de etiquetar. El middleware actual usa `request.url.path`.
* **Multiproceso y métricas duplicadas**: Asegura un **único registry multiproceso** y limpia `PROMETHEUS_MULTIPROC_DIR` al inicio.
* **pg_cron no ejecuta**: Verifica extensión instalada, permisos del rol y que el **scheduler** esté activo (`select * from cron.job`).

---

**Autor:** Ixchel Beristain
**Última actualización:** 08/11/2025

````

---


