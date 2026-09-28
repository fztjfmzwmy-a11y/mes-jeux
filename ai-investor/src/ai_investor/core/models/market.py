from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import AwareDatetime, Field, model_validator

from ai_investor.core.models._base import DomainModel
from ai_investor.core.money import Currency, PositiveDecimal
from ai_investor.core.provenance import Source


class PriceBar(DomainModel):
    """Cours journalier. Les incohérences internes sont refusées à la construction."""

    symbol: str
    day: date
    open: PositiveDecimal | None = None
    high: PositiveDecimal | None = None
    low: PositiveDecimal | None = None
    close: PositiveDecimal
    volume: int | None = Field(default=None, ge=0)
    currency: Currency
    adjusted: bool = False  # True si ajusté des splits / dividendes
    source: Source

    @model_validator(mode="after")
    def _consistent(self) -> PriceBar:
        if self.high is not None and self.low is not None:
            if self.high < self.low:
                raise ValueError(f"{self.symbol} {self.day}: plus haut < plus bas")
            for label, value in (("close", self.close), ("open", self.open)):
                if value is not None and not (self.low <= value <= self.high):
                    raise ValueError(f"{self.symbol} {self.day}: {label} hors de [bas, haut]")
        return self


class Quote(DomainModel):
    """Dernier prix connu, horodaté."""

    symbol: str
    price: PositiveDecimal
    currency: Currency
    as_of: AwareDatetime
    source: Source


class Fundamentals(DomainModel):
    """Données de valorisation, toutes facultatives : une valeur absente reste absente."""

    symbol: str
    as_of: AwareDatetime
    source: Source
    price_earnings: Decimal | None = None
    price_book: Decimal | None = None
    dividend_yield_percent: Decimal | None = None
    ev_ebitda: Decimal | None = None
    currency: Currency | None = None
