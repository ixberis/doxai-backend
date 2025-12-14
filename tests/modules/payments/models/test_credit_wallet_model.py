# backend/tests/modules/payments/models/test_credit_wallet_model.py

from sqlalchemy import UniqueConstraint
from app.modules.payments.models import CreditWallet

def test_tablename_and_columns():
    t = CreditWallet.__table__
    assert t.name == "wallets"
    # Columnas alineadas con SQL: id, user_id, balance, balance_reserved
    for col in ["id", "user_id", "balance", "balance_reserved"]:
        assert col in t.c
    # Verificar que user_id tiene constraint unique
    assert any(
        isinstance(c, UniqueConstraint) and "user_id" in [col.name for col in c.columns]
        for c in t.constraints
    ), "user_id debe tener constraint UNIQUE"

def test_available_credits():
    """Test método available_credits en v3."""
    w = CreditWallet(id=1, user_id=1, balance=500, balance_reserved=100)
    assert w.available_credits() == 400  # 500 - 100

def test_available_credits_zero_reserved():
    """Test available_credits sin reservas."""
    w = CreditWallet(id=1, user_id=1, balance=200, balance_reserved=0)
    assert w.available_credits() == 200
# end of backend/tests/modules/payments/models/test_credit_wallet_model.py
