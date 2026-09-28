"""Fournisseurs de portefeuille : saisie manuelle et fichiers importés (lecture seule)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ai_investor.core.enums import DataReliability
from ai_investor.core.models import CashBalance, Position
from ai_investor.data.importers.positions import load_positions_file
from ai_investor.data.interfaces import PortfolioDataProvider, ProviderInfo


class ManualPortfolioProvider(PortfolioDataProvider):
    """Positions saisies à la main par l'utilisateur."""

    def __init__(self, positions: Sequence[Position], cash: Sequence[CashBalance] = ()) -> None:
        self._positions = tuple(positions)
        self._cash = tuple(cash)

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name="saisie-manuelle",
            reliability=DataReliability.USER_PROVIDED,
            description="Positions saisies manuellement",
        )

    def get_positions(self) -> Sequence[Position]:
        return self._positions

    def get_cash_balances(self) -> Sequence[CashBalance]:
        return self._cash


class FilePortfolioProvider(PortfolioDataProvider):
    """Positions lues depuis un fichier CSV/JSON (relu à chaque appel)."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name=f"fichier:{self._path.name}",
            reliability=DataReliability.USER_PROVIDED,
            description="Fichier importé par l'utilisateur",
        )

    def get_positions(self) -> Sequence[Position]:
        return load_positions_file(self._path).positions

    def get_cash_balances(self) -> Sequence[CashBalance]:
        return load_positions_file(self._path).cash
