from datetime import timedelta
from decimal import Decimal as D

from ai_investor.data.validation import IssueLevel, check_quote, check_series
from tests.helpers import bars, quote


def run(series, now, currency="EUR"):
    return check_series(series, currency, now, D(25), 7, 3)


def codes(check):
    return {i.code for i in check.issues}


def test_clean_series(now):
    check = run(bars("X", [100, 101, 102, 103], now.date()), now)
    assert check.issues == () and len(check.bars) == 4


def test_spike_detected_not_removed(now):
    check = run(bars("X", [100, 101, 180, 102, 103], now.date()), now)
    assert codes(check) == {"SPIKE"} and len(check.issues) == 1  # le retour n'est pas re-signalé
    assert len(check.bars) == 5 and not check.critical


def test_real_jump_flagged_as_question(now):
    check = run(bars("X", [100, 100, 50, 51, 50], now.date()), now)
    assert codes(check) == {"JUMP"}
    assert "division" in check.issues[0].message


def test_unconfirmed_last_jump_is_critical(now):
    check = run(bars("X", [100, 101, 102, 160], now.date()), now)
    assert check.critical and codes(check) == {"UNCONFIRMED_LAST_JUMP"}


def test_gaps_stale_duplicates_currency(now):
    series = bars("X", [100, 101], now.date() - timedelta(days=20))
    series += bars("X", [102], now.date() - timedelta(days=10))
    dup = series[0].model_copy(update={"close": D(99)})
    usd = bars("X", [1], now.date(), currency="USD")
    check = run([*series, dup, *usd], now)
    assert {"GAP", "STALE", "CONFLICTING_DUPLICATE", "CURRENCY_MIX"} <= codes(check)
    assert len(check.bars) == 3


def test_future_and_empty(now):
    check = run(bars("X", [100, 101], now.date() + timedelta(days=1)), now)
    assert check.critical and "FUTURE_DATE" in codes(check)
    assert run([], now).critical


def test_quote_outlier(now):
    assert check_quote(quote("X", 100, now), D(98), D(25)) == []
    [issue] = check_quote(quote("X", 1000, now), D(100), D(25))
    assert issue.level == IssueLevel.CRITICAL
    assert check_quote(quote("X", 1000, now), None, D(25)) == []
