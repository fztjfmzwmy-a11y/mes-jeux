from __future__ import annotations

from pydantic import AwareDatetime, Field, model_validator

from ai_investor.core.models._base import DomainModel
from ai_investor.core.models.asset import Asset
from ai_investor.core.money import Currency, NonNegativeDecimal, PositiveDecimal


class Position(DomainModel):
    asset: Asset
    quantity: PositiveDecimal
    average_price: PositiveDecimal  # prix de revient unitaire, dans la devise de l'actif

    @property
    def cost_basis(self) -> PositiveDecimal:
        return self.quantity * self.average_price


class CashBalance(DomainModel):
    amount: NonNegativeDecimal
    currency: Currency


class PortfolioSnapshot(DomainModel):
    """Photographie d'un portefeuille à un instant donné."""

    name: str = Field(min_length=1)
    base_currency: Currency
    as_of: AwareDatetime
    positions: tuple[Position, ...] = ()
    cash: tuple[CashBalance, ...] = ()

    @model_validator(mode="after")
    def _no_duplicates(self) -> PortfolioSnapshot:
        keys = [p.asset.key for p in self.positions]
        duplicates = sorted({k for k in keys if keys.count(k) > 1})
        if duplicates:
            raise ValueError(f"Positions en double : {', '.join(duplicates)}")
        currencies = [c.currency for c in self.cash]
        if len(currencies) != len(set(currencies)):
            raise ValueError("Plusieurs soldes de liquidités dans la même devise")
        return self
