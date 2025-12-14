# -*- coding: utf-8 -*-
import pytest
from pydantic import ValidationError
from app.modules.payments.schemas.wallet_schemas import WalletOut

def test_wallet_out_valid_balances():
    w = WalletOut(
        id=1,
        user_id="user_123",
        balance=100,
        balance_reserved=20,
        balance_available=80,
    )
    assert w.user_id == "user_123"
    assert w.balance == 100
    assert w.balance_reserved == 20
    assert w.balance_available == 80

def test_wallet_out_invalid_negative_balance():
    with pytest.raises(ValidationError):
        WalletOut(
            id=1,
            user_id="user_123",
            balance=-1,
            balance_reserved=0,
            balance_available=-1,
        )
# Fin del archivo