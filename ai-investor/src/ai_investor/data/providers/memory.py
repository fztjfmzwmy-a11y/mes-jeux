"""Fournisseur de marché en mémoire (tests, données simulées, démonstrations)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date

from ai_investor.core.enums import DataReliability
from ai_investor.core.errors import ProviderUnavailableError
from ai_investor.core.models import Fundamentals, PriceBar, Quote
from ai_investor.data.interfaces import MarketDataProvider, ProviderInfo


class InMemoryMarketDataProvider(MarketDataProvider):
    def __init__(
        self,
        quotes: Iterable[Quote] = (),
        bars: Iterable[PriceBar] = (),
        name: str = "memoire",
        reliability: DataReliability = DataReliability.SIMULATED,
        available: bool = True,
        fundamentals: Iterable[Fundamentals] = (),
    ) -> None:
        self._fundamentals = {f.symbol.upper(): f for f in fundamentals}
        self._quotes: dict[str, Quote] = {}
        for quote in quotes:
            current = self._quotes.get(quote.symbol)
            if current is None or quote.as_of > current.as_of:
                self._quotes[quote.symbol] = quote
        self._bars: dict[str, list[PriceBar]] = {}
        for bar in bars:
            self._bars.setdefault(bar.symbol, []).append(bar)
        for series in self._bars.values():
            series.sort(key=lambda b: b.day)
        self._info = ProviderInfo(name=name, reliability=reliability)
        self.available = available  # permet de simuler une API indisponible

    @property
    def info(self) -> ProviderInfo:
        return self._info

    def _check(self) -> None:
        if not self.available:
            raise ProviderUnavailableError(f"Fournisseur {self._info.name} indisponible")

    def get_latest_price(self, symbol: str) -> Quote | None:
        self._check()
        return self._quotes.get(symbol.upper())

    def get_price_history(self, symbol: str, start: date, end: date) -> Sequence[PriceBar]:
        self._check()
        return [b for b in self._bars.get(symbol.upper(), []) if start <= b.day <= end]

    def get_fundamentals(self, symbol: str) -> Fundamentals | None:
        self._check()
        return self._fundamentals.get(symbol.upper())
