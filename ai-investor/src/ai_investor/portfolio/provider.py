"""Expose le portefeuille virtuel via l'interface PortfolioDataProvider."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from ai_investor.core.enums import DataReliability
from ai_investor.core.models import CashBalance, Position
from ai_investor.data.interfaces import PortfolioDataProvider, ProviderInfo
from ai_investor.portfolio.simulator import VirtualPortfolioService


class VirtualPortfolioProvider(PortfolioDataProvider):
    def __init__(
        self,
        service: VirtualPortfolioService,
        name: str,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._service = service
        self._name = name
        self._clock = clock

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name=f"portefeuille-virtuel:{self._name}",
            reliability=DataReliability.SIMULATED,
            description="Portefeuille simulé (aucun compte réel)",
        )

    def get_positions(self) -> Sequence[Position]:
        return self._service.snapshot(self._name, self._clock()).positions

    def get_cash_balances(self) -> Sequence[CashBalance]:
        return self._service.snapshot(self._name, self._clock()).cash
