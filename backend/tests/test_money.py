from __future__ import annotations

from decimal import Decimal

import pytest

from apps.core.money import Money


def test_arithmetic_within_currency():
    a = Money(Decimal("10.00"), "PLN")
    b = Money(Decimal("2.50"), "PLN")
    assert a + b == Money(Decimal("12.50"), "PLN")
    assert a - b == Money(Decimal("7.50"), "PLN")
    assert a * 3 == Money(Decimal("30.00"), "PLN")


def test_cross_currency_add_raises():
    with pytest.raises(ValueError):
        Money(Decimal("1"), "PLN") + Money(Decimal("1"), "EUR")


def test_zero_comparison_is_currency_agnostic():
    assert Money.zero("PLN") == 0
    assert Money.zero("EUR") == 0


def test_serialization_fixed_two_decimals():
    assert Money(Decimal("1"), "PLN").to_dict() == {"amount": "1.00", "currency": "PLN"}
