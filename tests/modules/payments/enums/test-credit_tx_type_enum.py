# -*- coding: utf-8 -*-
from app.modules.payments.enums import CreditTxType

def test_credit_tx_type_contains_core_operations_lowercase():
    expected = {"purchase", "consume", "adjust", "refund_reversal"}
    got = {m.value for m in CreditTxType}
    assert expected.issubset(got)
    for m in CreditTxType:
        assert m.value == m.value.lower()
# Fin del archivo