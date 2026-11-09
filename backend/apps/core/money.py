"""Money type — Decimal + ISO 4217 currency code.

Rules:
- Arithmetic across currencies raises ``ValueError``.
- Comparison with ``0`` is allowed (``amount == 0``) and currency-agnostic.
- Serializes to ``{"amount": "123.45", "currency": "PLN"}`` with a trailing
  string to keep JSON's number limitations out of our ledger.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Self

DEFAULT_CURRENCY = "PLN"
ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str = DEFAULT_CURRENCY

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            object.__setattr__(self, "amount", Decimal(str(self.amount)))
        object.__setattr__(self, "currency", self.currency.upper())

    @classmethod
    def zero(cls, currency: str = DEFAULT_CURRENCY) -> Self:
        return cls(ZERO, currency)

    def _same(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValueError(f"currency mismatch: {self.currency} vs {other.currency}")

    def __add__(self, other: "Money") -> "Money":
        self._same(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._same(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: Decimal | int | float) -> "Money":
        return Money(self.amount * Decimal(str(factor)), self.currency)

    def __neg__(self) -> "Money":
        return Money(-self.amount, self.currency)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (int, Decimal)) and other == 0:
            return self.amount == ZERO
        if isinstance(other, Money):
            return self.amount == other.amount and self.currency == other.currency
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.amount, self.currency))

    def to_dict(self) -> dict[str, str]:
        return {"amount": f"{self.amount:.2f}", "currency": self.currency}
