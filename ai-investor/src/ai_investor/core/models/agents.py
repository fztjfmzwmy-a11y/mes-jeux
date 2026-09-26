from __future__ import annotations

from typing import Any

from pydantic import AwareDatetime, Field, model_validator

from ai_investor.core.enums import AgentReportStatus, AgentVerdict
from ai_investor.core.models._base import DomainModel
from ai_investor.core.provenance import Source
from ai_investor.security.permissions import AgentRole


class DataReference(DomainModel):
    """Donnée utilisée par une analyse (pour la traçabilité)."""

    description: str
    source: Source
    as_of: AwareDatetime | None = None


class AgentReport(DomainModel):
    """Rapport d'un agent. Faits, interprétations et hypothèses sont séparés."""

    agent: AgentRole
    created_at: AwareDatetime
    status: AgentReportStatus
    verdict: AgentVerdict = AgentVerdict.NO_OPINION
    subject: str | None = None  # actif ou thème analysé
    summary: str = ""
    facts: tuple[str, ...] = ()
    interpretations: tuple[str, ...] = ()
    hypotheses: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    data_used: tuple[DataReference, ...] = ()
    errors: tuple[str, ...] = ()
    # Résultats structurés (JSON) destinés aux autres agents et au journal.
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _honest(self) -> AgentReport:
        if self.status != AgentReportStatus.OK and self.verdict not in (
            AgentVerdict.NO_OPINION,
            AgentVerdict.REVIEW_REQUIRED,
            AgentVerdict.BLOCK,
        ):
            raise ValueError(
                f"Un agent en statut {self.status} ne peut pas émettre l'avis {self.verdict}"
            )
        if self.status == AgentReportStatus.OK and not self.data_used:
            raise ValueError("Une analyse sans aucune donnée référencée ne peut pas être OK")
        if self.status == AgentReportStatus.UNAVAILABLE and not self.errors:
            raise ValueError("Agent indisponible : la cause doit être indiquée dans 'errors'")
        return self
