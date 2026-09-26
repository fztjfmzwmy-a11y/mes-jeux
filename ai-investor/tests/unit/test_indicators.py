from datetime import date
from decimal import Decimal as D

import pytest

from ai_investor.quant.indicators import (
    annualized_volatility,
    drawdown,
    period_return,
    simple_returns,
    sma,
    to_pct,
    value_on_or_before,
)


def test_simple_returns_and_sma():
    assert simple_returns([100, 110, 99]) == pytest.approx([0.1, -0.1])
    assert simple_returns([0, 10, 20]) == pytest.approx([1.0])  # base nulle ignorée
    assert sma([1, 2, 3, 4], 2) == 3.5
    assert sma([1, 2], 3) is None and sma([1], 0) is None


def test_volatility():
    assert annualized_volatility([0.01]) is None
    assert annualized_volatility([0.01, 0.01, 0.01]) == 0
    assert annualized_volatility([0.01, -0.01]) == pytest.approx(0.01414 * 15.8745, rel=1e-3)


def test_drawdown_known_values():
    dd = drawdown([100, 120, 90, 110])
    assert dd.maximum == pytest.approx(-0.25) and dd.current == pytest.approx(110 / 120 - 1)
    assert (dd.peak_index, dd.trough_index) == (1, 2)
    assert drawdown([]) is None
    assert drawdown([100, 101, 102]).maximum == 0


def test_period_return_never_extrapolates():
    series = [(date(2026, 1, 1), 100.0), (date(2026, 2, 1), 110.0), (date(2026, 3, 1), 121.0)]
    assert period_return(series, date(2026, 2, 1)) == pytest.approx(0.1)
    assert period_return(series, date(2026, 2, 15)) == pytest.approx(0.1)  # dernière valeur avant
    assert period_return(series, date(2025, 12, 1)) is None  # historique trop court
    assert value_on_or_before(series, date(2025, 1, 1)) is None


def test_to_pct():
    assert to_pct(0.123456) == D("12.35")
