import json
import math

import pytest

from ai_investor.agents.base import AgentContext, AnalysisRequest, run_agent
from ai_investor.agents.quant_agent import DISCLAIMER, QuantAgent
from ai_investor.config import load_config
from ai_investor.core.enums import AgentReportStatus, AgentVerdict
from ai_investor.core.errors import PermissionDeniedError
from ai_investor.data.providers.memory import InMemoryMarketDataProvider
from ai_investor.security.permissions import AgentRole
from tests.helpers import bars

CFG = load_config()


def ctx(now, history=(), **kw):
    return AgentContext(
        role=AgentRole.QUANT,
        settings=CFG.settings,
        risk_rules=CFG.risk_rules,
        _market=InMemoryMarketDataProvider((), history, **kw),
        clock=lambda: now,
    )


def series(n, drift, amp=0.01):
    return [100 * (1 + drift) ** i * (1 + amp * math.sin(i / 2)) for i in range(n)]


def analyze(context, subject="X", **params):
    return run_agent(QuantAgent(), context, AnalysisRequest(subject=subject, parameters=params))


def test_full_quant_report(now):
    report = analyze(ctx(now, bars("X", series(400, 0.001), now.date())))
    assert report.status == AgentReportStatus.OK
    m = report.payload
    for key in (
        "total_return",
        "cagr",
        "volatility",
        "max_drawdown",
        "sharpe",
        "moving_averages",
        "variations",
        "monte_carlo",
        "backtests",
    ):
        assert key in m
    assert [b["strategy"] for b in m["backtests"]] == ["Buy & Hold", "Filtre MM200"]
    assert DISCLAIMER in report.hypotheses and DISCLAIMER in report.summary
    assert DISCLAIMER in m["warnings"]
    assert any("indépendants" in h for h in report.hypotheses)
    json.dumps(m)


def test_verdicts(now):
    up = analyze(ctx(now, bars("X", series(400, 0.002), now.date())))
    assert up.verdict == AgentVerdict.BUY
    down = analyze(ctx(now, bars("X", series(400, -0.002), now.date())))
    assert down.verdict == AgentVerdict.WAIT


def test_strong_past_but_deep_drawdown_is_not_buy(now):
    closes = series(400, 0.003)[:350]
    closes += [closes[-1] * (0.99**i) for i in range(1, 51)]  # -40 % sur la fin
    report = analyze(ctx(now, bars("X", closes, now.date())))
    assert report.verdict != AgentVerdict.BUY


def test_monte_carlo_is_reproducible(now):
    history = bars("X", series(400, 0.001), now.date())
    a = analyze(ctx(now, history)).payload["monte_carlo"]
    b = analyze(ctx(now, history)).payload["monte_carlo"]
    assert a == b and a["seed"] == CFG.settings.MONTE_CARLO_SEED


def test_beta_against_benchmark(now):
    base = series(400, 0.0005, amp=0.02)
    rets = [base[i] / base[i - 1] - 1 for i in range(1, len(base))]
    levered = [100.0]
    for r in rets:
        levered.append(levered[-1] * (1 + 2 * r))
    history = bars("X", levered, now.date()) + bars("IDX", base, now.date())
    report = analyze(ctx(now, history), benchmark="IDX", universe=["IDX"])
    b = report.payload["benchmark"]
    assert b["beta"] == pytest.approx(2.0, abs=0.01) and b["correlation"] == pytest.approx(1.0)
    assert report.payload["correlations"]["X"]["IDX"] == pytest.approx(1.0)
    assert any("supérieure" in i for i in report.interpretations)


def test_insufficient_history(now):
    report = analyze(ctx(now, bars("X", series(100, 0.001), now.date())))
    assert report.status == AgentReportStatus.INSUFFICIENT_DATA
    assert report.verdict == AgentVerdict.NO_OPINION
    assert DISCLAIMER in report.hypotheses


def test_suspicious_last_price(now):
    closes = series(400, 0.001)
    closes[-1] *= 1.7
    report = analyze(ctx(now, bars("X", closes, now.date())))
    assert report.status == AgentReportStatus.INSUFFICIENT_DATA


def test_unavailable_and_missing_subject(now):
    assert analyze(ctx(now, available=False)).status == AgentReportStatus.INSUFFICIENT_DATA
    assert analyze(ctx(now), subject=None).status == AgentReportStatus.INSUFFICIENT_DATA


def test_quant_cannot_read_portfolio_or_news(now):
    context = ctx(now)
    with pytest.raises(PermissionDeniedError):
        _ = context.portfolio
    with pytest.raises(PermissionDeniedError):
        _ = context.news
