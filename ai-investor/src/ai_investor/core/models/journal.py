from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import AwareDatetime, Field, model_validator

from ai_investor.core.enums import Action, DecisionStatus, JournalEntryType
from ai_investor.core.models._base import DomainModel
from ai_investor.core.models.agents import DataReference
from ai_investor.core.money import Currency
from ai_investor.security.permissions import AgentRole


class JournalRecord(DomainModel):
    """Entrée du journal des décisions (section 14). Écrite une fois, jamais modifiée.

    Le « résultat ultérieur » est une entrée OUTCOME distincte qui référence la décision.
    """

    entry_type: JournalEntryType
    recorded_at: AwareDatetime
    symbol: str | None = None
    action: Action | None = None
    amount: Decimal | None = None
    price: Decimal | None = None
    currency: Currency | None = None
    agents_consulted: tuple[AgentRole, ...] = ()
    data_used: tuple[DataReference, ...] = ()
    reasoning: str = ""
    risks: tuple[str, ...] = ()
    final_status: DecisionStatus | None = None
    risk_rules: dict[str, Any] = Field(default_factory=dict)  # instantané des règles appliquées
    refers_to: int | None = None  # pour OUTCOME : numéro de la décision évaluée
    details: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _by_type(self) -> JournalRecord:
        if self.entry_type == JournalEntryType.DECISION:
            missing = [
                name
                for name, value in (
                    ("symbol", self.symbol),
                    ("action", self.action),
                    ("final_status", self.final_status),
                    ("agents_consulted", self.agents_consulted),
                    ("reasoning", self.reasoning),
                    ("risk_rules", self.risk_rules),
                )
                if not value
            ]
            if missing:
                raise ValueError(f"Entrée DECISION incomplète : {', '.join(missing)}")
        if self.entry_type == JournalEntryType.OUTCOME and self.refers_to is None:
            raise ValueError("Entrée OUTCOME : 'refers_to' (décision évaluée) obligatoire")
        if self.entry_type != JournalEntryType.OUTCOME and self.refers_to is not None:
            raise ValueError("'refers_to' est réservé aux entrées OUTCOME")
        return self
