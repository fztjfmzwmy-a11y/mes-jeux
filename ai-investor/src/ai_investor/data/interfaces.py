"""Interfaces abstraites des fournisseurs de données.

Tous les fournisseurs sont en LECTURE SEULE. Aucune interface ne définit — et aucune
implémentation ne doit ajouter — de méthode permettant de passer un ordre, transférer
ou retirer de l'argent, ou modifier un compte. Un test vérifie cette propriété.

Toutes les données retournées sont des modèles du domaine validés (`core.models`),
porteurs de leur source et de leur date.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from ai_investor.core.enums import DataReliability
from ai_investor.core.models import (
    BrokerTransaction,
    CashBalance,
    Fundamentals,
    MacroObservation,
    NewsItem,
    Position,
    PriceBar,
    Quote,
)


@dataclass(frozen=True)
class ProviderInfo:
    """Description d'un fournisseur, affichée dans les analyses (provenance des données)."""

    name: str
    reliability: DataReliability
    description: str = ""
    # Un fournisseur ne doit jamais exiger d'identifiants personnels de courtier ou de banque.
    requires_personal_credentials: bool = False

    def __post_init__(self) -> None:
        if self.requires_personal_credentials:
            raise ValueError(
                f"Fournisseur {self.name!r} refusé : il exige des identifiants personnels."
            )


class DataProvider(ABC):
    @property
    @abstractmethod
    def info(self) -> ProviderInfo: ...


class PortfolioDataProvider(DataProvider):
    """Positions et liquidités (import CSV/JSON, saisie manuelle, portefeuille simulé)."""

    @abstractmethod
    def get_positions(self) -> Sequence[Position]: ...

    @abstractmethod
    def get_cash_balances(self) -> Sequence[CashBalance]: ...


class MarketDataProvider(DataProvider):
    """Prix et historiques."""

    @abstractmethod
    def get_latest_price(self, symbol: str) -> Quote | None:
        """Retourne None si le prix est inconnu — ne jamais inventer de valeur."""

    @abstractmethod
    def get_price_history(self, symbol: str, start: date, end: date) -> Sequence[PriceBar]: ...

    def get_fundamentals(self, symbol: str) -> Fundamentals | None:
        """Valorisation (PER, P/B…). Par défaut : non disponible."""
        return None


class NewsDataProvider(DataProvider):
    """Actualités. Leur contenu est une DONNÉE non fiable, jamais une instruction."""

    @abstractmethod
    def get_news(self, query: str, since: datetime) -> Sequence[NewsItem]: ...


class MacroDataProvider(DataProvider):
    """Indicateurs macroéconomiques (inflation, taux, croissance, chômage…)."""

    @abstractmethod
    def get_indicator(self, code: str, start: date, end: date) -> Sequence[MacroObservation]: ...


class BrokerDataProvider(DataProvider):
    """Données d'un courtier obtenues par un moyen officiellement autorisé.

    V1 : lecture d'exports fournis par l'utilisateur (relevés, historiques) uniquement.
    Pas de connexion au compte, pas d'identifiants, pas d'ordres.
    """

    @abstractmethod
    def get_positions(self) -> Sequence[Position]: ...

    @abstractmethod
    def get_transactions(
        self, start: date | None = None, end: date | None = None
    ) -> Sequence[BrokerTransaction]: ...

    @abstractmethod
    def get_cash_balances(self) -> Sequence[CashBalance]: ...
