from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import Field

from ai_investor.core.models._base import DomainModel
from ai_investor.core.provenance import Source


class MacroObservation(DomainModel):
    code: str = Field(min_length=1)  # ex. "EA_HICP_YOY", "ECB_DEPOSIT_RATE"
    label: str
    period: date
    value: Decimal
    unit: str  # "%", "index", "EUR bn"…
    source: Source
