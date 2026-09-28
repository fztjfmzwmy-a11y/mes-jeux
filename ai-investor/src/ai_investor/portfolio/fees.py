"""Modèle de frais des opérations simulées."""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

from pydantic import BaseModel, ConfigDict, Field

from ai_investor.core.money import CENT


class FeeModel(BaseModel):
    """Frais = fixe + pourcentage du montant brut, arrondis au centime."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fixed: Decimal = Field(default=Decimal("0"), ge=0)
    percent: Decimal = Field(default=Decimal("0"), ge=0, le=10)

    def fee_for(self, gross_amount: Decimal) -> Decimal:
        fee = self.fixed + gross_amount * self.percent / Decimal(100)
        return fee.quantize(CENT, rounding=ROUND_HALF_EVEN)
