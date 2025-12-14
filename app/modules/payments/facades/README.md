# Facades de Pagos - Documentación

## Mejoras Implementadas (2025-10-25) ✅

### 1. Flujo Completo de Reembolsos ✅

**Antes:**
- `refund()` solo actualizaba estado interno
- No registraba modelo `Refund`
- No ejecutaba reembolso con proveedor
- No manejaba reversa de créditos

**Ahora:**
- ✅ Crea registro `Refund` en estado `PENDING`
- ✅ Ejecuta reembolso con adaptador del proveedor (Stripe/PayPal)
- ✅ Actualiza `Refund` con resultado del proveedor
- ✅ Registra reversa de créditos en `CreditTransaction`
- ✅ Actualiza estado del `Payment` (REFUNDED/PAID)
- ✅ Validaciones completas:
  - Suma de reembolsos ≤ `amount_cents`
  - Moneda coincidente con `Payment`
- ✅ Idempotencia mediante `idempotency_key`

**Ejemplo de uso:**

```python
from app.modules.payments.facades.payments_facade import refund

# Reembolso total
refund_obj, payment = await refund(
    db=db,
    payment_id=123,
    reason="customer_request",
    idempotency_key="refund-123-xyz"
)

# Reembolso parcial
refund_obj, payment = await refund(
    db=db,
    payment_id=123,
    amount_cents=5000,  # Parcial
    reason="partial_refund",
    idempotency_key="refund-123-abc"
)
```

---

### 2. Procesamiento de Webhooks de Reembolso ✅

**Nuevo archivo:** `webhooks_facade.py` (extendido)

**Funciones agregadas:**
- `is_refund_event()`: Detecta eventos de reembolso de Stripe/PayPal
- Soporte para eventos:
  - Stripe: `charge.refunded`, `refund.created`, `refund.updated`, `refund.failed`
  - PayPal: `PAYMENT.CAPTURE.REFUNDED`, `PAYMENT.REFUND.COMPLETED`, `PAYMENT.REFUND.FAILED`

**Uso:**
```python
if is_refund_event(provider, event_type):
    # Procesar webhook de reembolso
    # Actualizar estado de Refund existente
    pass
```

---

### 3. Vistas SQL de Diagnóstico ✅

**Nuevos archivos creados:**

#### `303_refunds_reconciliation.sql`
Vista para conciliación de reembolsos por pago:
- Cuenta de reembolsos por estado (pending, completed, failed, cancelled)
- Suma de montos reembolsados vs monto del pago
- Detección de inconsistencias (reembolsos que exceden el pago, etc.)
- Flags útiles: `is_fully_refunded`, `is_partially_refunded`, `has_pending_refunds`

```sql
-- Ver inconsistencias
SELECT * FROM vw_refunds_reconciliation WHERE integrity_check != 'OK';

-- Ver reembolsos parciales
SELECT * FROM vw_refunds_reconciliation WHERE is_partially_refunded;
```

#### `110_mv_refunds_daily.sql`
Vista materializada para KPIs de reembolsos:
- Reembolsos por día, proveedor y moneda
- Promedios y totales
- Tasa de éxito de reembolsos
- Breakdown por estado

```sql
-- Refrescar vista (ejecutar diariamente)
REFRESH MATERIALIZED VIEW mv_refunds_daily;

-- Ver tendencias
SELECT * FROM mv_refunds_daily 
WHERE day >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY day DESC;
```

#### `304_payments_vs_refunds_summary.sql`
Vista comparativa mensual de pagos vs reembolsos:
- Tasa de reembolso por cantidad y por monto
- Revenue neto (pagos - reembolsos)
- Promedios por proveedor
- Tendencias temporales

```sql
-- Ver tasa de reembolso por proveedor
SELECT 
  payment_provider,
  AVG(refund_rate_by_amount_pct) as avg_refund_rate
FROM vw_payments_vs_refunds_summary
WHERE month >= CURRENT_DATE - INTERVAL '6 months'
GROUP BY payment_provider;
```

---

### 4. Configuración Centralizada ✅

**Nuevo archivo:** `settings_payments.py`

**Configuración incluida:**
- Feature flags (payments_enabled, refunds_enabled)
- Credenciales Stripe y PayPal
- Límites de pagos y reembolsos
- Timeouts y reintentos
- Configuración de seguridad
- Sistema de créditos
- Notificaciones

**Uso:**
```python
from app.shared.config.settings_payments import get_payments_settings

settings = get_payments_settings()

if not settings.refunds_enabled:
    raise HTTPException(status_code=503, detail="Reembolsos deshabilitados")

if settings.allow_insecure_webhooks:
    logger.warning("⚠️ Webhooks inseguros habilitados - SOLO DESARROLLO")
```

---

### 5. Documentación de Secrets ✅

**Nuevo archivo:** `SECRETS_SETUP.md`

**Incluye:**
- Variables de entorno necesarias para Stripe y PayPal
- URLs de webhooks para desarrollo y producción
- Setup con Stripe CLI para testing local
- Proceso de rotación de secrets
- Comandos de troubleshooting
- Ejemplos de testing con Stripe CLI

**Secrets requeridos:**
```bash
# Stripe
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

# PayPal
PAYPAL_CLIENT_ID=...
PAYPAL_CLIENT_SECRET=...
PAYPAL_WEBHOOK_ID=...
```

---

## Estado Actual

### ✅ Completado

1. ✅ Modelo `Refund` con validaciones y constraints
2. ✅ Servicio `RefundService` para gestión de reembolsos
3. ✅ Adaptadores de proveedores (stubs documentados para implementación)
4. ✅ Flujo completo en `payments_facade.refund()`
5. ✅ Procesamiento de webhooks de reembolso
6. ✅ Vistas SQL de diagnóstico y KPIs
7. ✅ Configuración centralizada
8. ✅ Documentación de secrets y setup

### 🔄 Pendiente (Requiere implementación externa)

1. 🔄 **Implementar adaptadores reales** con SDKs de Stripe/PayPal
   - Reemplazar stubs en `refund_adapters.py`
   - Agregar manejo de errores específicos de cada proveedor
   
2. 🔄 **Configurar secrets** en entorno de producción
   - Agregar claves de API en Lovable Cloud / Supabase
   - Configurar webhooks en dashboards de Stripe/PayPal
   
3. 🔄 **Testing end-to-end**
   - Probar flujo completo con Stripe CLI
   - Validar webhooks en sandbox de PayPal
   
4. 🔄 **Migración de base de datos**
   - Ejecutar cuando haya BD disponible: `alembic upgrade head`

### 📋 Backlog (Baja prioridad)

- Notificaciones por email de reembolsos
- Inclusión de refunds en PDFs de recibos
- Dashboard de admin para gestión de reembolsos
- Webhooks de notificación a terceros

---

## Arquitectura de Reembolsos

```
┌─────────────────┐
│ API Endpoint    │
│ /refund         │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────┐
│ payments_facade.refund()        │
│                                 │
│ 1. Validar Payment              │
│ 2. Verificar idempotencia       │
│ 3. Validar límites              │
│ 4. Crear Refund (PENDING)       │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ refund_adapters.execute_refund()│
│                                 │
│ ├─ Stripe: stripe.Refund.create │
│ └─ PayPal: capture.refund()     │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ Actualizar Refund               │
│                                 │
│ - mark_refunded() / mark_failed()│
│ - Registrar provider_refund_id  │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ Reversa de Créditos             │
│                                 │
│ credit_service.consume_credits()│
│ operation_code="refund_reversal"│
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ Actualizar Payment              │
│                                 │
│ - REFUNDED (total)              │
│ - PAID (parcial)                │
└─────────────────────────────────┘
```

---

## Próximos Pasos

### Alta Prioridad
1. **Implementar adaptadores reales** de Stripe y PayPal
2. **Configurar secrets** para API keys de proveedores
3. **Testing end-to-end** del flujo de reembolsos

### Media Prioridad
4. **Webhooks de reembolso:** Procesar eventos `refund.updated` de Stripe
5. **Conciliación:** Incluir refunds en vistas de diagnóstico
6. **Notificaciones:** Email al usuario cuando se procesa un reembolso

### Baja Prioridad
7. **Recibos:** Incluir refunds en PDF de recibos
8. **Reportes:** Dashboard de reembolsos para admin

---

## Migración de Base de Datos

**Tabla `refunds` ya modelada** en `refund_models.py`:
- Ejecutar migración Alembic para crear tabla
- Índices: `payment_id`, `status`, `created_at`
- Constraints: unicidad por `(provider, provider_refund_id)` e idempotencia por `(payment_id, idempotency_key)`

```bash
# Generar migración
alembic revision --autogenerate -m "add_refunds_table"

# Aplicar migración
alembic upgrade head
```

---

## Seguridad y Auditoría

✅ **Idempotencia:** Previene duplicación de reembolsos  
✅ **Validaciones:** Límites y moneda verificados  
✅ **Trazabilidad:** Metadata completa en `Refund` y `PaymentEvent`  
✅ **Atomicidad:** Transacciones para garantizar consistencia  
✅ **Logging:** Registro detallado para debugging y auditoría  

---

## Contacto

**Autor:** DoxAI  
**Fecha:** 2025-10-25  
**Módulo:** `backend/app/modules/payments/facades`
