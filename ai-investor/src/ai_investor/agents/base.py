"""Socle commun des agents.

- Un agent ne reçoit que les fournisseurs autorisés par son rôle (`AgentContext`).
- Un agent ne produit que des rapports (`AgentReport`) : aucune action n'est possible.
- Une erreur interne n'interrompt jamais le système : elle devient un rapport
  UNAVAILABLE explicite (`run_agent`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ai_investor.config import RiskRules, Settings
from ai_investor.core.enums import AgentReportStatus
from ai_investor.core.errors import ForbiddenActionError, PermissionDeniedError
from ai_investor.core.models import AgentReport
from ai_investor.data.interfaces import (
    MacroDataProvider,
    MarketDataProvider,
    NewsDataProvider,
    PortfolioDataProvider,
)
from ai_investor.security.permissions import AgentRole, Permission, permissions_for


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class AgentContext:
    """Accès en lecture seule, filtré par les permissions du rôle."""

    role: AgentRole
    settings: Settings
    risk_rules: RiskRules
    _portfolio: PortfolioDataProvider | None = None
    _market: MarketDataProvider | None = None
    _news: NewsDataProvider | None = None
    _macro: MacroDataProvider | None = None
    clock: Callable[[], datetime] = field(default=utc_now)

    def _require(self, permission: Permission) -> None:
        if permission not in permissions_for(self.role):
            raise PermissionDeniedError(f"L'agent {self.role} n'a pas la permission {permission}")

    @property
    def portfolio(self) -> PortfolioDataProvider | None:
        self._require(Permission.READ_PORTFOLIO)
        return self._portfolio

    @property
    def market(self) -> MarketDataProvider | None:
        self._require(Permission.READ_MARKET)
        return self._market

    @property
    def macro(self) -> MacroDataProvider | None:
        self._require(Permission.READ_MARKET)
        return self._macro

    @property
    def news(self) -> NewsDataProvider | None:
        self._require(Permission.READ_NEWS)
        return self._news

    def now(self) -> datetime:
        return self.clock()


@dataclass(frozen=True)
class AnalysisRequest:
    """Demande d'analyse. `subject` = actif concerné (facultatif)."""

    subject: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)


class Agent(ABC):
    role: AgentRole

    @abstractmethod
    def analyze(self, context: AgentContext, request: AnalysisRequest) -> AgentReport: ...


def run_agent(agent: Agent, context: AgentContext, request: AnalysisRequest) -> AgentReport:
    """Exécute un agent ; toute exception devient un rapport UNAVAILABLE (jamais une opinion)."""
    if context.role != agent.role:
        raise PermissionDeniedError(
            f"Contexte {context.role} fourni à l'agent {agent.role} : refusé"
        )
    try:
        return agent.analyze(context, request)
    except (PermissionDeniedError, ForbiddenActionError):
        raise  # une violation de sécurité n'est jamais masquée en simple indisponibilité
    except Exception as exc:  # un agent défaillant ne doit pas faire tomber le système
        return AgentReport(
            agent=agent.role,
            created_at=context.now(),
            status=AgentReportStatus.UNAVAILABLE,
            subject=request.subject,
            summary="Agent indisponible : analyse non réalisée.",
            errors=(f"{type(exc).__name__}: {exc}",),
        )
