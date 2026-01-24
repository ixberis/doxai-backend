# Alertmanager: Opciones de Canal

## Opción 1: Slack Webhook

### Requisitos
1. Crear Slack App con Incoming Webhooks habilitado
2. Generar webhook URL por canal

### Configuración receiver

```yaml
receivers:
  - name: 'ops-warning'
    slack_configs:
      - api_url: '${SLACK_WEBHOOK_URL_WARNING}'
        channel: '${SLACK_CHANNEL_WARNING}'
        username: 'DoxAI Alertmanager'
        icon_emoji: ':warning:'
        send_resolved: true
        title: '{{ .Status | toUpper }}: {{ .CommonAnnotations.summary }}'
        text: >-
          {{ range .Alerts }}
          *Alert:* {{ .Annotations.summary }}
          *Module:* {{ .Labels.module }}
          *Severity:* {{ .Labels.severity }}
          *Details:* {{ .Annotations.description }}
          *Runbook:* {{ .Annotations.runbook_url }}
          {{ end }}
        # Colores por status
        color: '{{ if eq .Status "firing" }}danger{{ else }}good{{ end }}'
        
  - name: 'ops-info'
    slack_configs:
      - api_url: '${SLACK_WEBHOOK_URL_INFO}'
        channel: '${SLACK_CHANNEL_INFO}'
        username: 'DoxAI Alertmanager'
        icon_emoji: ':information_source:'
        send_resolved: true
```

### Variables de entorno requeridas
```bash
# Slack webhooks (obtener desde Slack App > Incoming Webhooks)
SLACK_WEBHOOK_URL_WARNING=<tu-webhook-url-warning>
SLACK_WEBHOOK_URL_INFO=<tu-webhook-url-info>
SLACK_CHANNEL_WARNING=#doxai-alerts-warning
SLACK_CHANNEL_INFO=#doxai-alerts-info
```

---

## Opción 2: Email (SMTP)

### Requisitos
1. Servidor SMTP accesible (SendGrid, SES, Mailgun, o propio)
2. Credenciales SMTP

### Configuración global + receivers

```yaml
global:
  smtp_smarthost: '${SMTP_HOST}:${SMTP_PORT}'
  smtp_from: '${SMTP_FROM}'
  smtp_auth_username: '${SMTP_USER}'
  smtp_auth_password: '${SMTP_PASSWORD}'
  smtp_require_tls: true

receivers:
  - name: 'ops-warning'
    email_configs:
      - to: '${OPS_EMAIL_WARNING}'
        send_resolved: true
        headers:
          Subject: '[DoxAI WARNING] {{ .CommonAnnotations.summary }}'
        html: |
          <h2>{{ .Status | toUpper }}: {{ .CommonAnnotations.summary }}</h2>
          {{ range .Alerts }}
          <p><strong>Alert:</strong> {{ .Annotations.summary }}</p>
          <p><strong>Module:</strong> {{ .Labels.module }}</p>
          <p><strong>Details:</strong> {{ .Annotations.description }}</p>
          <hr>
          {{ end }}
        
  - name: 'ops-info'
    email_configs:
      - to: '${OPS_EMAIL_INFO}'
        send_resolved: true
        headers:
          Subject: '[DoxAI INFO] {{ .CommonAnnotations.summary }}'
```

### Variables de entorno requeridas
```bash
# SMTP config (ejemplo: SendGrid, SES, Mailgun)
SMTP_HOST=<tu-smtp-host>
SMTP_PORT=587
SMTP_FROM=<tu-email-from>
SMTP_USER=<tu-smtp-user>
SMTP_PASSWORD=<tu-smtp-password>

# Destinatarios
OPS_EMAIL_WARNING=<email-equipo-ops>
OPS_EMAIL_INFO=<email-info-ops>
```

---

## Valores recomendados por severidad

| Parámetro | WARNING | INFO | Justificación |
|-----------|---------|------|---------------|
| `repeat_interval` | 4h | 12h | Warning requiere atención más frecuente |
| `group_wait` | 30s | 30s | Esperar agrupación antes de enviar |
| `group_interval` | 5m | 5m | Tiempo entre actualizaciones de grupo |

---

## Generación del archivo final

⚠️ **NUNCA** commitear secrets en el repo.

### Usando envsubst

```bash
# 1. Exportar variables de entorno
export SLACK_WEBHOOK_URL_WARNING="https://hooks.slack.com/services/..."
export SLACK_WEBHOOK_URL_INFO="https://hooks.slack.com/services/..."
# ... resto de variables

# 2. Generar archivo final
envsubst < alertmanager.yml.template > alertmanager.yml

# 3. Validar configuración
amtool check-config alertmanager.yml
```

### Alternativas seguras
1. **Variables de entorno** en el runtime (Railway, Docker, etc.)
2. **Secrets manager** (Vault, AWS Secrets Manager)
3. **Docker secrets** para Swarm/Kubernetes
