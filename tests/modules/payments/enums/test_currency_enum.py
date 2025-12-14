# -*- coding: utf-8 -*-
import pytest
from app.modules.payments.enums import Currency

def test_currency_contains_expected_codes_lowercase():
    assert Currency.USD.value == "usd"
    assert Currency.MXN.value == "mxn"
    for c in Currency:
        assert c.value == c.value.lower()

@pytest.mark.parametrize("code", ["usd", "mxn"])
def test_currency_roundtrip_by_value(code):
    member = Currency(code)
    assert member.value == code
# Fin del archivo