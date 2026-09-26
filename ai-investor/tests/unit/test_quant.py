import math
from datetime import date, timedelta
from decimal import Decimal as D

import pytest

from ai_investor.portfolio.fees import FeeModel
from ai_investor.quant.backtest import (
    WARNINGS,
    BuyAndHold,
    MovingAverageFilter,
    Strategy,
    run_backtest,
)
from ai_investor.quant.monte_carlo import simulate
from ai_investor.quant.risk_metrics import (
    aligned_returns,
    beta,
    cagr,
    correlation_matrix,
    sharpe_ratio,
    total_return,
)

DAY0 = date(2024, 1, 1)


def days(n):
    return [DAY0 + timedelta(days=i) for i in range(n)]


# --- Mesures ------------------------------------------------------------------------


def test_total_return_and_cagr():
    assert total_return([100, 150]) == pytest.approx(0.5)
    assert total_return([100]) is None
    assert cagr([100, 200], 365) == pytest.approx(2 ** (365.25 / 365) - 1)
    assert cagr([100, 0], 365) is None


def test_sharpe_known_value():
    rets = [0.01, -0.005] * 50
    mean, sd = 0.0025, math.sqrt(sum((r - 0.0025) ** 2 for r in rets) / 99)
    assert sharpe_ratio(rets) == pytest.approx(mean / sd * math.sqrt(252))
    assert sharpe_ratio([0.01, 0.01]) is None  # écart-type nul : non défini
    assert sharpe_ratio([0.01]) is None
    assert sharpe_ratio(rets, 0.05) < sharpe_ratio(rets)


def test_beta_and_correlation():
    market = [0.01, -0.02, 0.015, 0.0, -0.01, 0.02]
    levered = [2 * r for r in market]
    assert beta(levered, market) == pytest.approx(2.0)
    assert beta(market, [0.0] * 6) is None
    assert beta(market, market[:3]) is None
    a = {DAY0 + timedelta(days=i): 100 * (1.01**i) * (1 + 0.02 * (i % 2)) for i in range(40)}
    b = {d: 2 * v for d, v in a.items()}
    m = correlation_matrix({"A": a, "B": b, "C": {DAY0: 1.0}}, 20)
    assert m["A"]["B"] == pytest.approx(1.0) and m["A"]["A"] == 1.0
    assert m["A"]["C"] is None  # pas assez d'observations communes
    ra, rb = aligned_returns(a, {DAY0: 1.0, DAY0 + timedelta(days=1): 2.0})
    assert len(ra) == len(rb) == 1


# --- Monte Carlo --------------------------------------------------------------------


def test_monte_carlo_reproducible_and_bounded():
    rets = [0.01, -0.02, 0.005, 0.015, -0.01] * 20
    a = simulate(rets, 60, 500, seed=7)
    b = simulate(rets, 60, 500, seed=7)
    c = simulate(rets, 60, 500, seed=8)
    assert a == b and a.percentiles != c.percentiles
    p = a.percentiles
    assert p["P5"] <= p["P25"] <= p["P50"] <= p["P75"] <= p["P95"]
    assert 0 <= a.probability_of_loss <= 1
    assert a.worst_max_drawdown_p95 <= a.median_max_drawdown <= 0
    assert any("indépendants" in h for h in a.assumptions)


def test_monte_carlo_constant_returns():
    r = simulate([0.001, 0.001], 100, 200, seed=1)
    assert r.percentiles["P5"] == pytest.approx(1.001**100 - 1)
    assert r.probability_of_loss == 0 and r.median_max_drawdown == 0


@pytest.mark.parametrize("args", [([0.01], 10, 10), ([0.01, 0.02], 0, 10), ([0.1, 0.2], 10, 0)])
def test_monte_carlo_invalid(args):
    with pytest.raises(ValueError):
        simulate(*args, seed=0)


# --- Backtests ----------------------------------------------------------------------


def test_buy_and_hold_matches_price_minus_fees():
    closes = [100.0, 110.0, 121.0]
    r = run_backtest(days(3), closes, BuyAndHold(), 1000.0, FeeModel(fixed=D(1)))
    # achat au cours du jour 1 (110) avec 999 € nets, valeur finale 999/110*121
    assert r.final_value == pytest.approx(999 / 110 * 121)
    assert r.trades == 1 and r.fees_paid == 1.0
    assert r.warnings == WARNINGS
    assert WARNINGS[0] == "PERFORMANCE HISTORIQUE ≠ PERFORMANCE FUTURE"


class Spy(Strategy):
    name = "espion"

    def __init__(self):
        self.seen = []

    def target_exposure(self, past_closes):
        self.seen.append(tuple(past_closes))
        return 1.0


def test_strategy_never_sees_the_future():
    closes = [float(100 + i) for i in range(10)]
    spy = Spy()
    run_backtest(days(10), closes, spy, 1000.0, FeeModel())
    for t, past in enumerate(spy.seen, start=1):
        assert past == tuple(closes[:t])  # seulement jusqu'à la veille


def test_changing_future_prices_does_not_change_past_decisions():
    base = [100.0 + 5 * math.sin(i / 4) + i * 0.3 for i in range(120)]
    altered = base[:80] + [p * 3 for p in base[80:]]
    a = run_backtest(days(120), base, MovingAverageFilter(20), 1000.0, FeeModel())
    b = run_backtest(days(120), altered, MovingAverageFilter(20), 1000.0, FeeModel())
    assert a.equity[:80] == b.equity[:80]


def test_moving_average_filter_waits_without_history():
    closes = [100.0 + i for i in range(10)]
    r = run_backtest(days(10), closes, MovingAverageFilter(50), 1000.0, FeeModel(fixed=D(1)))
    assert r.trades == 0 and r.final_value == 1000.0 and r.exposure == 0


def test_filter_exits_in_downtrend_and_counts_fees():
    closes = [100.0 + i for i in range(40)] + [140.0 - 3 * i for i in range(1, 30)]
    r = run_backtest(
        days(len(closes)), closes, MovingAverageFilter(10), 1000.0, FeeModel(fixed=D(1))
    )
    bh = run_backtest(days(len(closes)), closes, BuyAndHold(), 1000.0, FeeModel(fixed=D(1)))
    assert r.trades >= 2 and r.fees_paid == r.trades * 1.0
    assert r.max_drawdown > bh.max_drawdown  # drawdown moins sévère sur CETTE série


@pytest.mark.parametrize(
    "d,c",
    [
        (days(3), [1.0, 2.0]),
        ([DAY0, DAY0, DAY0 + timedelta(days=1)], [1.0, 2.0, 3.0]),
        (days(1), [1.0]),
    ],
)
def test_backtest_rejects_bad_input(d, c):
    with pytest.raises(ValueError):
        run_backtest(d, c, BuyAndHold(), 1000.0, FeeModel())
