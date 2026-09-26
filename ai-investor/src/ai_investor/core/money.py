"""Montants monétaires : Decimal + devise, jamais de conversion implicite."""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

CENT = Decimal("0.01")


def _upper_currency(value: str) -> str:
    value = value.strip().upper()
    if len(value) != 3 or not value.isalpha():
        raise ValueError(f"Code devise ISO 4217 invalide : {value!r}")
    return value


Currency = Annotated[str, AfterValidator(_upper_currency)]
PositiveDecimal = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
NonNegativeDecimal = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]


class CurrencyMismatchError(ValueError):
    pass


class Money(BaseModel):
    model_config = ConfigDict(frozen=True)

    amount: Annotated[Decimal, Field(allow_inf_nan=False)]
    currency: Currency

    def _check(self, other: Money) -> None:
        if other.currency != self.currency:
            raise CurrencyMismatchError(
                f"Devises différentes ({self.currency} / {other.currency}) : "
                "conversion explicite requise."
            )

    def __add__(self, other: Money) -> Money:
        self._check(other)
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check(other)
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def rounded(self) -> Money:
        return Money(
            amount=self.amount.quantize(CENT, rounding=ROUND_HALF_EVEN), currency=self.currency
        )
