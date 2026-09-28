from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from ai_investor.core.identifiers import is_valid_isin, normalize_isin
from ai_investor.core.money import CurrencyMismatchError, Money
from ai_investor.core.provenance import DataPoint


@pytest.mark.parametrize("isin", ["US0378331005", "IE00B4L5Y983", "FR0000120271"])
def test_valid_isin(isin):
    assert is_valid_isin(isin)


@pytest.mark.parametrize("isin", ["US0378331006", "US037833100", "us0378331005x", "", "1234"])
def test_invalid_isin(isin):
    assert not is_valid_isin(isin)


def test_isin_normalized():
    assert normalize_isin(" us0378331005 ") == "US0378331005"


def test_money_is_exact_and_refuses_currency_mix():
    total = Money(amount=Decimal("0.1"), currency="eur") + Money(
        amount=Decimal("0.2"), currency="EUR"
    )
    assert total == Money(amount=Decimal("0.3"), currency="EUR")
    with pytest.raises(CurrencyMismatchError):
        _ = total + Money(amount=Decimal("1"), currency="USD")


@pytest.mark.parametrize("amount", ["NaN", "Infinity"])
def test_money_refuses_nan(amount):
    with pytest.raises(ValidationError):
        Money(amount=Decimal(amount), currency="EUR")


def test_money_refuses_bad_currency():
    with pytest.raises(ValidationError):
        Money(amount=Decimal(1), currency="EURO")


def test_missing_value_requires_reason(source, now):
    with pytest.raises(ValidationError, match="missing_reason"):
        DataPoint[Decimal](value=None, source=source, fetched_at=now)
    point = DataPoint[Decimal](
        value=None, source=source, fetched_at=now, missing_reason="non publié"
    )
    assert point.is_missing


def test_value_with_missing_reason_is_incoherent(source, now):
    with pytest.raises(ValidationError):
        DataPoint[Decimal](value=Decimal(1), source=source, fetched_at=now, missing_reason="x")


def test_future_dated_data_rejected(source, now):
    with pytest.raises(ValidationError, match="futur"):
        DataPoint[Decimal](
            value=Decimal(1), source=source, fetched_at=now, as_of=now + timedelta(days=1)
        )


def test_naive_datetime_rejected(source):
    with pytest.raises(ValidationError):
        DataPoint[Decimal](value=Decimal(1), source=source, fetched_at=datetime(2026, 1, 1))


def test_staleness(source, now):
    fresh = DataPoint[Decimal](value=Decimal(1), source=source, fetched_at=now, as_of=now)
    old = DataPoint[Decimal](
        value=Decimal(1), source=source, fetched_at=now, as_of=now - timedelta(days=10)
    )
    undated = DataPoint[Decimal](value=Decimal(1), source=source, fetched_at=now)
    later = now + timedelta(hours=1)
    assert not fresh.is_stale(later, timedelta(days=3))
    assert old.is_stale(later, timedelta(days=3))
    assert undated.is_stale(later, timedelta(days=3))
    assert now.tzinfo is UTC
