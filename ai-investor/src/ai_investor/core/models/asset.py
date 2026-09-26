from __future__ import annotations

from pydantic import Field, field_validator

from ai_investor.core.enums import AssetType
from ai_investor.core.identifiers import normalize_isin
from ai_investor.core.models._base import DomainModel
from ai_investor.core.money import Currency


class Asset(DomainModel):
    symbol: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1)
    asset_type: AssetType
    currency: Currency
    isin: str | None = None
    sector: str | None = None  # None = inconnu (jamais deviné)
    region: str | None = None
    country: str | None = None
    # Pour les ETF : indice suivi, utile pour détecter les doublons entre ETF.
    tracked_index: str | None = None

    @field_validator("symbol")
    @classmethod
    def _symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("isin")
    @classmethod
    def _isin(cls, value: str | None) -> str | None:
        return None if value is None else normalize_isin(value)

    @property
    def key(self) -> str:
        """Identifiant stable : ISIN si connu, sinon symbole."""
        return self.isin or self.symbol
