from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from ai_investor.core.enums import (
    Action,
    AgentVerdict,
    DecisionStatus,
    QualityLevel,
    RiskOutcome,
)
from ai_investor.core.models._base import DomainModel
from ai_investor.core.models.agents import DataReference
from ai_investor.core.money import Money, PositiveDecimal
from ai_investor.security.permissions import AgentRole

_MOVEMENTS = frozenset({Action.BUY, Action.SELL, Action.REDUCE})


class Proposal(DomainModel):
    """Proposition du Strategist (section 9). Ne peut jamais être exécutée."""

    created_at: AwareDatetime
    symbol: str
    action: Action
    amount: Money | None = None
    quantity: PositiveDecimal | None = None
    reference_price: Money | None = None
    horizon: str = Field(min_length=1)
    reasoning: str = Field(min_length=1)
    risks: tuple[str, ...] = Field(min_length=1)
    favorable_scenario: str = Field(min_length=1)
    unfavorable_scenario: str = Field(min_length=1)
    portfolio_impact: str = Field(min_length=1)
    uncertainty: QualityLevel
    data_used: tuple[DataReference, ...] = Field(min_length=1)
    simulated: Literal[True] = True

    @model_validator(mode="after")
    def _movement_is_quantified(self) -> Proposal:
        if self.action in _MOVEMENTS:
            if self.amount is None and self.quantity is None:
                raise ValueError(f"{self.action} : montant ou quantité simulés obligatoires")
            if self.reference_price is None:
                raise ValueError(f"{self.action} : prix de référence obligatoire")
        if self.amount is not None and self.amount.amount <= 0:
            raise ValueError("Le montant simulé doit être positif")
        return self


class RiskCheck(DomainModel):
    rule: str
    outcome: RiskOutcome
    message: str = Field(min_length=1)
    observed: str | None = None
    limit: str | None = None


class RiskVerdict(DomainModel):
    created_at: AwareDatetime
    status: Literal[DecisionStatus.APPROVED, DecisionStatus.BLOCKED]
    checks: tuple[RiskCheck, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _block_is_binding(self) -> RiskVerdict:
        blocked = any(c.outcome == RiskOutcome.BLOCK for c in self.checks)
        if blocked != (self.status == DecisionStatus.BLOCKED):
            raise ValueError("Le statut doit être BLOCKED si et seulement si une règle bloque")
        return self


class FinalDecision(DomainModel):
    """DÉCISION SIMULÉE produite par le Final Review. Jamais une certitude."""

    created_at: AwareDatetime
    symbol: str
    status: DecisionStatus
    proposed_action: Action
    amount: Money | None = None
    justification: str = Field(min_length=1)
    risks: tuple[str, ...] = ()
    cancel_conditions: tuple[str, ...] = ()
    data_quality: QualityLevel
    decision_quality: QualityLevel
    votes: dict[AgentRole, AgentVerdict] = Field(default_factory=dict)
    simulated: Literal[True] = True

    @model_validator(mode="after")
    def _safety_invariants(self) -> FinalDecision:
        # Filet de sécurité au niveau du modèle : aucun vote ne peut contourner un blocage.
        risk_blocked = self.votes.get(AgentRole.RISK_MANAGER) == AgentVerdict.BLOCK
        if risk_blocked and self.status != DecisionStatus.BLOCKED:
            raise ValueError("Risk Manager = BLOCK impose FINAL = BLOCKED")
        review = self.votes.get(AgentRole.DEVILS_ADVOCATE) == AgentVerdict.REVIEW_REQUIRED
        if review and self.status not in (DecisionStatus.BLOCKED, DecisionStatus.REVIEW_REQUIRED):
            raise ValueError("Devil's Advocate = REVIEW_REQUIRED interdit une validation")
        if self.status == DecisionStatus.APPROVED:
            if self.votes.get(AgentRole.RISK_MANAGER) != AgentVerdict.APPROVED:
                raise ValueError("Validation impossible sans accord explicite du Risk Manager")
            if self.data_quality == QualityLevel.LOW:
                raise ValueError("Validation impossible avec une qualité de données LOW")
            if not self.cancel_conditions:
                raise ValueError("Une décision validée doit indiquer ses conditions d'annulation")
            if not self.risks:
                raise ValueError("Une décision validée doit indiquer ses risques")
        return self
