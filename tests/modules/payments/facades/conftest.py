# -*- coding: utf-8 -*-
"""
backend/tests/modules/payments/facades/conftest.py

Fixtures compartidos para tests de facades.
Re-exporta fixtures desde el conftest de fixtures para hacerlos disponibles.
"""

import pytest
from types import SimpleNamespace

from app.modules.payments.enums import PaymentProvider, Currency, PaymentStatus


class EnumLike:
    """Mock de enum que soporta .value y comparaciones con enums reales."""
    def __init__(self, value, enum_class):
        self._value = value
        self._enum_class = enum_class
    
    @property
    def value(self):
        return self._value
    
    def __eq__(self, other):
        # Soporta comparación con enum real o con string
        if hasattr(other, 'value'):
            return self._value == other.value
        return self._value == other
    
    def __hash__(self):
        # Necesario para usar en comparaciones 'in' con tuplas/sets
        return hash(self._value)
    
    def __repr__(self):
        return f"<{self._enum_class.__name__}.{self._value.upper()}>"
    
    def __str__(self):
        return self._value


@pytest.fixture
def make_payment():
    """
    Factory mínima para construir un 'Payment' sintético compatible con los tests.
    No toca BD; devuelve un objeto tipo namespace con los atributos que usan los tests.
    """
    def _make(**kwargs):
        # Defaults
        provider = kwargs.pop("provider", PaymentProvider.STRIPE)
        currency = kwargs.pop("currency", Currency.USD)
        status = kwargs.pop("status", PaymentStatus.SUCCEEDED)

        # Normaliza provider
        if hasattr(provider, "value"):
            provider_val = provider.value
        else:
            try:
                provider_val = PaymentProvider(provider).value
            except Exception:
                provider_val = str(provider).lower()

        # Normaliza currency
        if hasattr(currency, "value"):
            currency_val = currency.value
        else:
            try:
                currency_val = Currency(currency).value
            except Exception:
                currency_val = str(currency).lower()

        # Normaliza status (.value requerido en tests)
        if hasattr(status, "value"):
            status_val = status.value
        else:
            try:
                status_val = PaymentStatus(status).value
            except Exception:
                status_val = str(status).lower()

        data = dict(
            id=kwargs.pop("id", 1),
            user_id=kwargs.pop("user_id", 1),
            amount_cents=kwargs.pop("amount_cents", 1000),
            currency=EnumLike(currency_val.lower(), Currency),
            status=EnumLike(status_val, PaymentStatus),
            credits_purchased=kwargs.pop("credits_purchased", 10),
            provider=EnumLike(provider_val, PaymentProvider),
            provider_payment_id=kwargs.pop("provider_payment_id", "pi_stub"),
            provider_transaction_id=kwargs.pop("provider_transaction_id", "ch_stub"),
            payment_metadata=kwargs.pop("payment_metadata", {}),
            created_at=kwargs.pop("created_at", None),
        )
        # Cualquier extra que pasen los tests
        data.update(kwargs)
        return SimpleNamespace(**data)

    return _make


class DummyAsyncSession:
    """AsyncSession stub con commit/rollback/begin_nested/flush."""
    def __init__(self):
        self._commits = 0
        self._rollbacks = 0
        self._flushes = 0
        self._begun = False

    async def flush(self):
        """Simula flush() de AsyncSession."""
        self._flushes += 1

    async def commit(self):
        self._commits += 1

    async def rollback(self):
        self._rollbacks += 1

    async def execute(self, stmt):
        class R:
            def scalars(self_inner):
                class S:
                    def all(self_s):
                        return []
                return S()
            def scalar_one_or_none(self_inner):
                return None
        return R()

    def begin_nested(self):
        class Ctx:
            async def __aenter__(self_inner):
                return self_inner
            async def __aexit__(self_inner, exc_type, exc, tb):
                return False
        return Ctx()


@pytest.fixture
def db():
    """Fixture de base de datos dummy para tests de facades."""
    return DummyAsyncSession()


# Fin del archivo
