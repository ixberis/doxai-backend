# Integración Prometheus ↔ Alertmanager

## 1. Configuración prometheus.yml

Agregar al archivo `prometheus.yml` existente:

```yaml
# ═══════════════════════════════════════════════════════════════════════════════
# ALERTING: Conexión con Alertmanager
# ═══════════════════════════════════════════════════════════════════════════════
alerting:
  alertmanagers:
    - static_configs:
        - targets:
            # Si Alertmanager corre en el mismo host
            - 'localhost:9093'
            # Si corre en Docker/Railway
            # - 'alertmanager:9093'
      # Timeout para enviar alertas
      timeout: 10s

# ═══════════════════════════════════════════════════════════════════════════════
# RULE FILES: Archivos con reglas de alerta
# ═══════════════════════════════════════════════════════════════════════════════
rule_files:
  # Alertas DoxAI (archivos, storage, jobs)
  - '/etc/prometheus/rules/prometheus_alerts.yaml'
  # Agregar más archivos de reglas aquí si es necesario
  # - '/etc/prometheus/rules/other_alerts.yaml'
```

## 2. Estructura de archivos recomendada

```
/etc/prometheus/
├── prometheus.yml              # Config principal
└── rules/
    └── prometheus_alerts.yaml  # Reglas DoxAI (copiar de backend/app/monitoring/)

/etc/alertmanager/
├── alertmanager.yml           # Config Alertmanager
└── templates/                  # (opcional) Templates personalizados
    └── doxai.tmpl
```

## 3. Docker Compose (ejemplo completo)

```yaml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:v2.48.0
    container_name: prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./rules:/etc/prometheus/rules:ro
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.enable-lifecycle'  # Permite reload via API
    restart: unless-stopped

  alertmanager:
    image: prom/alertmanager:v0.26.0
    container_name: alertmanager
    ports:
      - "9093:9093"
    volumes:
      - ./alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
      - alertmanager_data:/alertmanager
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'
      - '--storage.path=/alertmanager'
    restart: unless-stopped

  # Backend DoxAI (expone /metrics)
  doxai-backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DB_METRICS_REFRESH_ENABLED=1
      - DB_METRICS_REFRESH_INTERVAL_SECONDS=60

volumes:
  prometheus_data:
  alertmanager_data:
```

## 4. Scrape config para DoxAI backend

Agregar a `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'doxai-backend'
    scrape_interval: 15s
    static_configs:
      - targets: ['doxai-backend:8000']
    metrics_path: '/metrics'
```

## 5. Railway / VPS deployment

### Railway
1. Crear servicio desde Docker image `prom/alertmanager:v0.26.0`
2. Montar `alertmanager.yml` como config file
3. Exponer puerto 9093 (internal)
4. Configurar variables de entorno para secrets

### VPS (systemd)
```bash
# /etc/systemd/system/alertmanager.service
[Unit]
Description=Alertmanager
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/alertmanager \
  --config.file=/etc/alertmanager/alertmanager.yml \
  --storage.path=/var/lib/alertmanager
Restart=always

[Install]
WantedBy=multi-user.target
```

## 6. Verificar conexión

```bash
# Prometheus debe mostrar Alertmanager como target
curl -s http://localhost:9090/api/v1/alertmanagers | jq .

# Debe retornar algo como:
# {
#   "status": "success",
#   "data": {
#     "activeAlertmanagers": [
#       { "url": "http://localhost:9093/api/v2/alerts" }
#     ]
#   }
# }
```
