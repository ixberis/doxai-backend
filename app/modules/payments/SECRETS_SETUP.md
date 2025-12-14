# Configuración de Secrets para Pagos

## Variables de Entorno Requeridas

### Stripe

```bash
# Claves de API
STRIPE_SECRET_KEY=sk_test_...              # O sk_live_... en producción
STRIPE_PUBLISHABLE_KEY=pk_test_...         # O pk_live_... en producción

# Webhooks
STRIPE_WEBHOOK_SECRET=whsec_...            # Secret para validar webhooks

# Configuración
STRIPE_ENABLED=true
STRIPE_WEBHOOK_TOLERANCE_SECONDS=300       # 5 minutos (default)
```

**Dónde obtener:**
1. Dashboard de Stripe: https://dashboard.stripe.com/apikeys
2. Webhooks: https://dashboard.stripe.com/webhooks

**Eventos a configurar en webhook:**
- `checkout.session.completed`
- `payment_intent.succeeded`
- `charge.succeeded`
- `charge.refunded`
- `refund.created`
- `refund.updated`
- `refund.failed`

---

### PayPal

```bash
# Claves de API
PAYPAL_CLIENT_ID=...                       # Client ID de PayPal
PAYPAL_CLIENT_SECRET=...                   # Client Secret de PayPal

# Configuración
PAYPAL_ENABLED=true
PAYPAL_MODE=sandbox                        # O 'live' en producción
PAYPAL_WEBHOOK_ID=...                      # ID del webhook para validación
```

**Dónde obtener:**
1. Dashboard de PayPal: https://developer.paypal.com/dashboard/applications
2. Crear app → REST API credentials
3. Webhooks: https://developer.paypal.com/dashboard/webhooks

**Eventos a configurar en webhook:**
- `PAYMENT.CAPTURE.COMPLETED`
- `CHECKOUT.ORDER.APPROVED`
- `PAYMENT.CAPTURE.REFUNDED`
- `PAYMENT.REFUND.COMPLETED`
- `PAYMENT.REFUND.FAILED`

---

### Configuración General

```bash
# Feature Flags
PAYMENTS_ENABLED=true
REFUNDS_ENABLED=true

# Límites
MIN_PAYMENT_AMOUNT_CENTS=100               # $1.00 mínimo
MAX_PAYMENT_AMOUNT_CENTS=10000000          # $100,000 máximo
ALLOW_PARTIAL_REFUNDS=true
MAX_REFUNDS_PER_PAYMENT=10

# Seguridad
ALLOW_INSECURE_WEBHOOKS=false              # NUNCA true en producción
REQUIRE_IDEMPOTENCY_KEYS=true

# Créditos
CREDITS_PER_DOLLAR=100                     # 1 USD = 100 créditos
WELCOME_CREDITS=50

# Notificaciones
SEND_PAYMENT_CONFIRMATION_EMAIL=true
SEND_REFUND_NOTIFICATION_EMAIL=true
```

---

## Setup en Desarrollo

### 1. Archivo `.env`

Crear `.env` en la raíz del proyecto:

```bash
# Copiar desde .env.example
cp .env.example .env

# Editar con tus claves
nano .env
```

### 2. Stripe CLI (para testing local)

```bash
# Instalar Stripe CLI
brew install stripe/stripe-cli/stripe

# Login
stripe login

#Forward webhooks a tu servidor local
stripe listen --forward-to http://localhost:8000/api/webhooks/stripe

# Copiar el webhook signing secret que aparece y agregarlo a .env
STRIPE_WEBHOOK_SECRET=whsec_...
```

### 3. PayPal Sandbox

```bash
# Usar credenciales de sandbox
PAYPAL_MODE=sandbox
PAYPAL_CLIENT_ID=<sandbox_client_id>
PAYPAL_CLIENT_SECRET=<sandbox_client_secret>
```

---

## Setup en Producción

### 1. Lovable Cloud / Supabase Secrets

```bash
# En Lovable Cloud o Supabase Edge Functions
# Agregar secrets mediante la UI o CLI

# Supabase CLI
supabase secrets set STRIPE_SECRET_KEY=sk_live_...
supabase secrets set STRIPE_WEBHOOK_SECRET=whsec_...
supabase secrets set PAYPAL_CLIENT_ID=...
supabase secrets set PAYPAL_CLIENT_SECRET=...
```

### 2. Validación de Secrets

```python
from app.shared.config.settings_payments import get_payments_settings

settings = get_payments_settings()

# Verificar que existan
assert settings.stripe_secret_key, "STRIPE_SECRET_KEY no configurado"
assert settings.stripe_webhook_secret, "STRIPE_WEBHOOK_SECRET no configurado"
assert settings.paypal_client_id, "PAYPAL_CLIENT_ID no configurado"
assert settings.paypal_client_secret, "PAYPAL_CLIENT_SECRET no configurado"

# Verificar que sean de producción
assert settings.stripe_secret_key.startswith("sk_live_"), "Usar claves de producción"
assert not settings.allow_insecure_webhooks, "Webhooks inseguros en producción"
```

### 3. Rotación de Secrets

**Frecuencia recomendada:** Cada 90 días

**Proceso:**
1. Generar nuevo secret en dashboard del proveedor
2. Actualizar en Lovable Cloud / Supabase
3. Verificar que funcione
4. Revocar secret anterior

---

## Webhooks URLs

### Desarrollo (con ngrok o similar)

```bash
# Stripe
https://<your-domain>.ngrok.io/api/webhooks/stripe

# PayPal
https://<your-domain>.ngrok.io/api/webhooks/paypal
```

### Producción

```bash
# Stripe
https://api.yourdomain.com/api/webhooks/stripe

# PayPal
https://api.yourdomain.com/api/webhooks/paypal
```

---

## Testing de Webhooks

### Stripe CLI

```bash
# Trigger evento de pago exitoso
stripe trigger checkout.session.completed

# Trigger evento de reembolso
stripe trigger charge.refunded

# Ver logs
stripe logs tail
```

### PayPal Sandbox

```bash
# Usar el PayPal Sandbox para simular transacciones
# https://developer.paypal.com/tools/sandbox/accounts/

# Crear orden de prueba
# Aprobar con cuenta de comprador sandbox
# Verificar webhook en dashboard
```

---

## Monitoreo

### Logs a revisar

```bash
# Verificar recepción de webhooks
grep "Webhook recibido" logs/payments.log

# Verificar procesamiento exitoso
grep "Webhook procesado exitosamente" logs/payments.log

# Verificar errores
grep "ERROR" logs/payments.log | grep webhook
```

### Métricas importantes

- Tasa de éxito de webhooks (> 99%)
- Tiempo de procesamiento de webhooks (< 5s)
- Reembolsos pendientes (monitorear)
- Discrepancias en conciliación (vw_refunds_reconciliation)

---

## Troubleshooting

### Webhook no recibido

1. Verificar URL en dashboard del proveedor
2. Verificar que el endpoint responda 200
3. Verificar firewalls / CORS
4. Verificar logs del servidor

### Error de firma inválida

1. Verificar STRIPE_WEBHOOK_SECRET / PAYPAL_WEBHOOK_ID
2. Verificar que no haya espacios extra
3. Verificar que sea el secret correcto (test vs live)

### Reembolso falla

1. Verificar logs: `grep "Error ejecutando reembolso" logs/payments.log`
2. Verificar saldo suficiente en cuenta del proveedor
3. Verificar que el pago sea reembolsable (no dispute, no chargeback)
4. Verificar límites de reembolso (suma no debe exceder payment.amount_cents)

---

## Contacto y Soporte

**Stripe Support:** https://support.stripe.com  
**PayPal Developer Support:** https://developer.paypal.com/support

**Documentación de APIs:**
- Stripe: https://stripe.com/docs/api
- PayPal: https://developer.paypal.com/docs/api/overview/

---

**Última actualización:** 2025-10-25  
**Autor:** DoxAI
