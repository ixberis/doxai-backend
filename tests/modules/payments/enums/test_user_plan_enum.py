# -*- coding: utf-8 -*-
from app.modules.payments.enums import UserPlan

def test_user_plan_is_lowercase_and_contains_minimum_tiers():
    expected_subset = {"free", "starter", "pro", "enterprise"}
    got = {m.value for m in UserPlan}
    assert expected_subset.issubset(got)
    for m in UserPlan:
        assert m.value == m.value.lower()
# Fin del archivo