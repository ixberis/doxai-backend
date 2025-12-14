# Módulo Payments - DoxAI

Módulo de gestión de pagos y créditos para DoxAI (migrado a arquitectura modular).

## Estructura

```
payments/
├── __init__.py
├── models/              # Modelos ORM
│   ├── __init__.py
│   ├── payment_models.py          # Registros de pagos
│   ├── credit_balances_models.py  # Saldo de créditos por usuario
│   └── credit_ledger_models.py    # Ledger de transacciones
│
├── schemas/             # Schemas Pydantic
│   ├── __init__.py
│   ├── payment_schemas.py         # Requests/Responses de pagos
│   └── credit_schemas.py          # Requests/Responses de créditos
│
├── services/            # Lógica de negocio
│   ├── __init__.py
│   ├── payment_service.py         # Gestión de pagos
│   ├── credit_service.py          # Gestión de créditos
│   └── paypal/                    # Integración PayPal (legacy)
│
├── routes/              # Endpoints FastAPI (pendiente)
│   └── __init__.py
│
└── tests/               # Tests unitarios (pendiente)
    └── __init__.py
```

## Funcionalidades

### 1. Gestión de Pagos
- **Creación de registros**: Almacenamiento de transacciones de pago
- **Actualización de estados**: CREATED → PENDING → COMPLETED / FAILED
- **Consulta de historial**: Pagos por usuario con filtros
- **Integración con proveedores**: PayPal, Stripe (preparado)

### 2. Sistema de Créditos
- **Balance por usuario**: Un registro único por usuario con créditos disponibles/reservados
- **Transacciones en ledger**: Historial completo de créditos/débitos
- **Tipos de operación**:
  - `CREDIT`: Recarga de créditos (desde pago)
  - `DEBIT`: Consumo de créditos (operaciones)
  - `REVERSAL`: Reversión de transacción
  - `EXPIRE`: Expiración de créditos
  - `ADJUST`: Ajuste manual

### 3. Proveedores de Pago
- **PayPal**: Suscripciones y pagos únicos
- **Stripe**: Preparado (pendiente implementación completa)

## Modelos

### PaymentRecord
```python
- payment_id: UUID (PK)
- user_id: UUID (FK → users)
- billing_session_id: UUID (para tracking)
- payment_order_id: String (ID en proveedor)
- payment_reference_id: String
- payment_transaction_id: String
- payment_amount: Decimal(10,2)
- payment_currency: currency_enum (usd, mxn, etc.)
- payment_provider: payment_provider_enum (paypal, stripe)
- payment_method: String ("PayPal", "Credit Card")
- payment_status: payment_status_enum (created, pending, completed, failed)
- payment_date: DateTime (cuando se completó)
- payment_created_at: DateTime
- payment_updated_at: DateTime
- payment_details: JSONB (metadata del proveedor)
- payment_url: Text (URL de checkout)
- redirected_to_paypal: Boolean
```

### CreditBalance
```python
- credit_balance_id: UUID (PK)
- user_id: UUID (FK → users, UNIQUE)
- credits_available: Integer (créditos disponibles)
- credits_reserved: Integer (créditos reservados en uso)
- created_at: DateTime
- updated_at: DateTime

@property balance_effective: int
# Retorna credits_available - credits_reserved
```

### CreditLedger
```python
- credit_ledger_id: UUID (PK)
- user_id: UUID (FK → users)
- tx_type: credit_tx_type_enum (credit, debit, reversal, expire, adjust)
- credits: Integer (cantidad movida, siempre positivo)
- payment_id: UUID (FK → payment_records, opcional)
- job_id: UUID (ID de trabajo asociado, opcional)
- operation_code: Text (código de operación, ej. 'RAG_ANALYZE')
- ext_provider: payment_provider_enum (opcional)
- ext_payment_id: Text (ID en proveedor externo, opcional)
- metadata: JSONB (información adicional)
- created_at: DateTime

# Constraint: UNIQUE(ext_provider, ext_payment_id) WHERE tx_type = 'credit'
# Previene doble abono por el mismo pago externo
```

## Servicios

### PaymentService
```python
create_payment_record(user_id, amount, currency, ...)
  # Crea un nuevo registro de pago
  
update_payment_status(payment_id, new_status)
  # Actualiza el estado de un pago
  
get_payment_by_id(payment_id)
  # Obtiene un pago por ID
  
get_payments_by_user(user_id)
  # Lista todos los pagos de un usuario
  
get_completed_payments_by_user(user_id)
  # Pagos completados solamente
  
mark_as_redirected(payment_id)
  # Marca que el usuario fue redirigido al proveedor
```

### CreditService
```python
get_or_create_balance(user_id)
  # Obtiene o crea el balance de créditos
  
add_credits(user_id, credits, payment_id?, ...)
  # Agrega créditos y registra en ledger
  
consume_credits(user_id, credits, operation_code, ...)
  # Consume créditos y registra en ledger
  # Raises HTTP 402 si no hay suficientes créditos
  
get_balance(user_id)
  # Obtiene el balance actual
  
get_ledger_history(user_id, limit=50)
  # Historial de transacciones del usuario
```

## Schemas

### Payment Schemas
- `CreatePaymentRequest`: Crear nuevo pago
- `ProcessPaymentRequest`: Procesar pago existente
- `PaymentRecordOut`: Representación de pago
- `PaymentResponse`: Respuesta de operación
- `PaymentListResponse`: Lista de pagos

### Credit Schemas
- `AddCreditsRequest`: Agregar créditos
- `ReserveCreditsRequest`: Reservar créditos
- `ConsumeCreditsRequest`: Consumir créditos
- `CreditBalanceOut`: Balance de usuario
- `CreditTransactionOut`: Transacción en ledger
- `CreditOperationResponse`: Respuesta de operación

## Uso

### Crear un Pago
```python
from app.modules.payments.services import PaymentService

payment_service = PaymentService(db)
payment = payment_service.create_payment_record(
    user_id=user.user_id,
    amount=99.99,
    currency="USD",
    provider=PaymentProvider.PAYPAL,
    order_id="PAYPAL_ORDER_123",
    reference_id="REF_456",
    transaction_id="TXN_789",
    payment_url="https://paypal.com/checkout/..."
)
```

### Agregar Créditos desde Pago
```python
from app.modules.payments.services import CreditService

credit_service = CreditService(db)
balance, tx = credit_service.add_credits(
    user_id=user.user_id,
    credits=1000,
    payment_id=payment.payment_id,
    ext_provider=PaymentProvider.PAYPAL,
    ext_payment_id="PAYPAL_TXN_123"
)

print(f"Nuevo balance: {balance.credits_available}")
```

### Consumir Créditos
```python
try:
    balance, tx = credit_service.consume_credits(
        user_id=user.user_id,
    credits=50,
    operation_code="RAG_ANALYZE",
    payment_metadata={"file_id": "abc-123"}
)
except HTTPException as e:
    # HTTP 402: Créditos insuficientes
    print(f"Error: {e.detail}")
```

## Seguridad

### Validaciones
- Montos de pago > 0
- Créditos siempre >= 0 en balance
- Balance efectivo calculado: `available - reserved`
- Unique constraint para evitar doble abono por pago externo

### RLS (Row Level Security)
Ver políticas de seguridad en:
- `database/rls/040_payment_records_policies.sql`
- `database/rls/050_credit_balances_policies.sql`
- `database/rls/051_credit_ledger_policies.sql`

**Importante**: 
- Usuarios solo ven sus propios pagos y créditos
- Ledger es append-only para usuarios
- Admin tiene acceso completo vía service_role

## Dependencias

- **Shared**: config, enums, utils, database
- **Auth**: Integración con módulo de usuarios
- **External**: PayPal API, Stripe API (futuro)

## Estado de Migración

✅ **Completado (60%)**:
- Models ORM migrados
- Schemas Pydantic creados
- Services consolidados (PaymentService, CreditService)

⏳ **Pendiente (40%)**:
- Routes consolidadas
- Tests unitarios
- Integración completa con Stripe

## Tests

```bash
# Pendiente implementación
pytest backend/app/modules/payments/tests/ -v
```

## Próximas Mejoras

- [ ] Routes RESTful para pagos y créditos
- [ ] Tests unitarios completos
- [ ] Integración Stripe completa
- [ ] Sistema de reserva de créditos con expiración
- [ ] Webhooks consolidados de proveedores
- [ ] Panel de administración de créditos
- [ ] Reportes de ingresos y consumo
