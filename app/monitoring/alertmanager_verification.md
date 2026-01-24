# Verificación Alertmanager: Checklist y Comandos

## 0. Generar archivo desde template

```bash
# El archivo alertmanager.yml.template usa variables ${VAR}
# Generar archivo final con envsubst:

export SLACK_WEBHOOK_URL_WARNING="<tu-webhook>"
export SLACK_WEBHOOK_URL_INFO="<tu-webhook>"
export SLACK_CHANNEL_WARNING="#doxai-alerts-warning"
export SLACK_CHANNEL_INFO="#doxai-alerts-info"
# ... o para SMTP:
export SMTP_HOST="<tu-host>"
export SMTP_PORT="587"
# ... resto de variables

envsubst < alertmanager.yml.template > alertmanager.yml
```

## 1. Validar configuración

### Con amtool (recomendado)
```bash
# Instalar amtool (viene con alertmanager)
amtool check-config alertmanager.yml

# Output esperado:
# Checking 'alertmanager.yml'  SUCCESS
```

### Con Docker
```bash
docker run --rm -v $(pwd)/alertmanager.yml:/etc/alertmanager/alertmanager.yml \
  prom/alertmanager:v0.26.0 \
  --config.file=/etc/alertmanager/alertmanager.yml \
  --check-config
```

## 2. Levantar Alertmanager

### Local
```bash
alertmanager --config.file=alertmanager.yml --storage.path=/tmp/alertmanager
```

### Docker
```bash
docker run -d --name alertmanager \
  -p 9093:9093 \
  -v $(pwd)/alertmanager.yml:/etc/alertmanager/alertmanager.yml \
  prom/alertmanager:v0.26.0
```

### Verificar que está corriendo
```bash
curl -s http://localhost:9093/-/healthy
# OK

curl -s http://localhost:9093/-/ready
# OK
```

## 3. Enviar alerta de prueba (manual)

### Con curl (API v2)
```bash
curl -X POST http://localhost:9093/api/v2/alerts \
  -H "Content-Type: application/json" \
  -d '[
    {
      "labels": {
        "alertname": "TestAlert",
        "severity": "warning",
        "module": "files",
        "team": "files"
      },
      "annotations": {
        "summary": "Alerta de prueba DoxAI",
        "description": "Esta es una alerta de prueba para verificar el routing."
      },
      "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
      "generatorURL": "http://localhost:9090/graph"
    }
  ]'

# Response: (vacío = éxito)
```

### Con amtool
```bash
amtool alert add \
  alertname=TestAlert \
  severity=warning \
  module=files \
  team=files \
  --annotation.summary="Alerta de prueba DoxAI" \
  --annotation.description="Prueba de routing por severidad"
```

## 4. Verificar estado de alertas

### Listar alertas activas
```bash
curl -s http://localhost:9093/api/v2/alerts | jq .

# O con amtool
amtool alert
```

### Ver silences activos
```bash
amtool silence query
```

### Ver status del cluster
```bash
curl -s http://localhost:9093/api/v2/status | jq .
```

## 5. Verificar recepción en canal

### Slack
- La alerta debe aparecer en el canal configurado
- Verificar formato del mensaje (labels, annotations)
- Confirmar que "resolved" también llega cuando se resuelve

### Email
- Revisar inbox (y spam)
- Verificar subject y body
- Confirmar que SMTP está funcionando

## 6. Resolver alerta de prueba

```bash
curl -X POST http://localhost:9093/api/v2/alerts \
  -H "Content-Type: application/json" \
  -d '[
    {
      "labels": {
        "alertname": "TestAlert",
        "severity": "warning",
        "module": "files",
        "team": "files"
      },
      "endsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
    }
  ]'
```

## 7. Checklist completo

- [ ] `amtool check-config alertmanager.yml` → SUCCESS
- [ ] Alertmanager corriendo (`/-/healthy` → OK)
- [ ] Prometheus conectado (`/api/v1/alertmanagers` muestra target)
- [ ] Alerta de prueba enviada (curl o amtool)
- [ ] Alerta recibida en canal (Slack/Email)
- [ ] Alerta resuelta recibida en canal
- [ ] Inhibition funciona (enviar warning + info, solo llega warning)
- [ ] Agrupación funciona (enviar 2 alertas mismo module, llegan juntas)

## 8. Troubleshooting

### Alertas no llegan
```bash
# Ver logs de Alertmanager
docker logs alertmanager

# Verificar routing (qué receiver recibiría esta alerta)
amtool config routes test \
  alertname=FilesDeleteErrorRateHigh \
  severity=warning \
  module=files
```

### Webhook Slack falla
```bash
# Probar webhook directamente (reemplazar con tu URL real)
curl -X POST -H 'Content-type: application/json' \
  --data '{"text":"Test desde curl"}' \
  "${SLACK_WEBHOOK_URL_WARNING}"
```

### SMTP falla
```bash
# Verificar conectividad
telnet smtp.sendgrid.net 587

# Ver logs de Alertmanager para errores SMTP
docker logs alertmanager 2>&1 | grep -i smtp
```

## 9. Reload config sin reiniciar

```bash
# Vía API (si --web.enable-lifecycle está habilitado)
curl -X POST http://localhost:9093/-/reload

# O con signal
kill -HUP $(pgrep alertmanager)
```
