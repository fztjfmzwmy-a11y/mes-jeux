"""Constructeurs de données de test."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal as D

from ai_investor.core.enums import AssetType, DataReliability
from ai_investor.core.models import Asset, CashBalance, Position, PriceBar, Quote
from ai_investor.core.provenance import Source

SRC = Source(name="test", reliability=DataReliability.SIMULATED)


def asset(symbol, asset_type=AssetType.STOCK, currency="EUR", **kw):
    return Asset(
        symbol=symbol, name=f"{symbol} test", asset_type=asset_type, currency=currency, **kw
    )


def position(symbol, qty, avg, **kw):
    return Position(asset=asset(symbol, **kw), quantity=D(qty), average_price=D(avg))


def cash(amount, currency="EUR"):
    return CashBalance(amount=D(amount), currency=currency)


def quote(symbol, price, as_of, currency="EUR"):
    return Quote(symbol=symbol, price=D(price), currency=currency, as_of=as_of, source=SRC)


def bars(symbol, closes, end: date, currency="EUR"):
    """Série journalière (jours calendaires) se terminant à `end`."""
    n = len(closes)
    return [
        PriceBar(
            symbol=symbol,
            day=end - timedelta(days=n - 1 - i),
            close=D(str(c)),
            currency=currency,
            source=SRC,
        )
        for i, c in enumerate(closes)
    ]


def end_of(day: date) -> datetime:
    return datetime.combine(day, time(23, 59), tzinfo=UTC)
