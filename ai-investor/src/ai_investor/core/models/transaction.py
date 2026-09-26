from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from ai_investor.core.enums import MOVEMENT_OPERATIONS, BrokerOperation, SimulatedOperation
from ai_investor.core.models._base import DomainModel
from ai_investor.core.money import Currency, NonNegativeDecimal, PositiveDecimal
from ai_investor.core.provenance import Source

_CASH_OPERATIONS = frozenset({SimulatedOperation.DEPOSIT, SimulatedOperation.WITHDRAWAL})


class SimulatedTransaction(DomainModel):
    """Transaction du portefeuille VIRTUEL. N'a aucun effet sur un compte réel."""

    portfolio: str = Field(min_length=1)
    executed_at: AwareDatetime
    operation: SimulatedOperation
    currency: Currency
    symbol: str | None = None
    quantity: PositiveDecimal | None = None
    price: PositiveDecimal | None = None
    amount: PositiveDecimal | None = None  # uniquement pour DEPOSIT / WITHDRAWAL
    fees: NonNegativeDecimal = Decimal("0")
    decision_ref: int | None = None  # numéro d'entrée du journal ayant motivé l'opération
    note: str = ""
    simulated: Literal[True] = True

    @model_validator(mode="after")
    def _fields_match_operation(self) -> SimulatedTransaction:
        op = self.operation
        if op in MOVEMENT_OPERATIONS:
            if not (self.symbol and self.quantity and self.price):
                raise ValueError(f"{op} : symbole, quantité et prix sont obligatoires")
            if self.amount is not None:
                raise ValueError(f"{op} : 'amount' est réservé aux mouvements de liquidités")
        elif op in _CASH_OPERATIONS:
            if self.amount is None or self.symbol or self.quantity or self.price:
                raise ValueError(f"{op} : seul 'amount' est attendu")
        else:  # HOLD / WAIT : décision enregistrée sans mouvement
            if not self.symbol or self.quantity or self.price or self.amount or self.fees:
                raise ValueError(f"{op} : seul le symbole est attendu (aucun mouvement)")
        return self

    @property
    def gross_value(self) -> Decimal:
        if self.quantity is not None and self.price is not None:
            return self.quantity * self.price
        return self.amount or Decimal("0")


class BrokerTransaction(DomainModel):
    """Opération HISTORIQUE réelle, lue depuis un export fourni par l'utilisateur.

    Donnée en lecture seule : elle décrit le passé, elle ne déclenche rien.
    """

    executed_at: AwareDatetime
    operation: BrokerOperation
    currency: Currency
    symbol: str | None = None
    isin: str | None = None
    quantity: PositiveDecimal | None = None
    price: PositiveDecimal | None = None
    amount: Decimal | None = None  # montant net signé tel qu'indiqué dans l'export
    fees: NonNegativeDecimal = Decimal("0")
    source: Source
