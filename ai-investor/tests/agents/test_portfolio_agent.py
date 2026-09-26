from datetime import timedelta
from decimal import Decimal as D

import pytest

from ai_investor.agents.base import AgentContext, AnalysisRequest, run_agent
from ai_investor.agents.portfolio_agent import PortfolioAgent
from ai_investor.config import load_config
from ai_investor.core.enums import AgentReportStatus, AgentVerdict
from ai_investor.core.errors import PermissionDeniedError
from ai_investor.data.providers.files import ManualPortfolioProvider
from ai_investor.data.providers.memory import InMemoryMarketDataProvider
from ai_investor.security.permissions import AgentRole
from tests.helpers import bars, cash, position, quote

CFG = load_config()


def context(now, positions, cash_, quotes=(), history=(), role=AgentRole.PORTFOLIO, **kw):
    return AgentContext(
        role=role,
        settings=CFG.settings,
        risk_rules=CFG.risk_rules,
        _portfolio=ManualPortfolioProvider(positions, cash_),
        _market=InMemoryMarketDataProvider(quotes, history, **kw),
        clock=lambda: now,
    )


def balanced(now):
    ps = [position(f"S{i}", 1, 90, sector=f"Sect{i}") for i in range(12)]
    qs = [quote(p.asset.symbol, 100, now) for p in ps]
    hist = [
        b for p in ps for b in bars(p.asset.symbol, [100 + (i % 3) for i in range(25)], now.date())
    ]
    return ps, qs, hist


def test_full_report(now):
    ps, qs, hist = balanced(now)
    report = run_agent(
        PortfolioAgent(), context(now, ps, [cash(200)], qs, hist), AnalysisRequest(subject="s3")
    )
    assert report.status == AgentReportStatus.OK
    assert report.verdict == AgentVerdict.HOLD and report.subject == "S3"
    assert report.facts[0].startswith("Valeur totale : 1400.00 EUR")
    assert report.payload["valuation_complete"] is True
    assert report.payload["data_quality"] == "HIGH"
    assert len(report.data_used) == 13  # portefeuille + 12 prix
    assert report.hypotheses  # l'hypothèse des quantités constantes est explicite


def test_verdict_reduce_for_oversized_position(now):
    ps = [position("BIG", 10, 100), position("SMALL", 1, 100)]
    qs = [quote("BIG", 100, now), quote("SMALL", 100, now)]
    report = run_agent(
        PortfolioAgent(), context(now, ps, [cash(500)], qs), AnalysisRequest(subject="BIG")
    )
    assert report.verdict == AgentVerdict.REDUCE
    assert any("BIG pèse" in r for r in report.risks)


def test_no_opinion_on_unheld_asset_or_without_subject(now):
    ps, qs, _ = balanced(now)
    ctx = context(now, ps, [cash(200)], qs)
    assert run_agent(PortfolioAgent(), ctx, AnalysisRequest("NEW")).verdict == "NO_OPINION"
    assert run_agent(PortfolioAgent(), ctx, AnalysisRequest()).verdict == "NO_OPINION"


def test_missing_price_gives_insufficient_data(now):
    ps, qs, _ = balanced(now)
    report = run_agent(
        PortfolioAgent(), context(now, ps, [cash(200)], qs[1:]), AnalysisRequest(subject="S3")
    )
    assert report.status == AgentReportStatus.INSUFFICIENT_DATA
    assert report.verdict == AgentVerdict.NO_OPINION
    assert "INCONNUE" in report.facts[0]
    assert any("S0" in e for e in report.errors)


def test_market_api_unavailable(now):
    ps, qs, _ = balanced(now)
    report = run_agent(
        PortfolioAgent(), context(now, ps, [cash(200)], qs, available=False), AnalysisRequest()
    )
    assert report.status == AgentReportStatus.INSUFFICIENT_DATA
    assert any("indisponible" in e for e in report.errors)


def test_no_portfolio_source(now):
    ctx = AgentContext(
        role=AgentRole.PORTFOLIO,
        settings=CFG.settings,
        risk_rules=CFG.risk_rules,
        clock=lambda: now,
    )
    report = run_agent(PortfolioAgent(), ctx, AnalysisRequest())
    assert report.status == AgentReportStatus.INSUFFICIENT_DATA


def test_agent_crash_becomes_unavailable(now):
    class Broken(ManualPortfolioProvider):
        def get_positions(self):
            raise RuntimeError("fichier corrompu")

    ctx = AgentContext(
        role=AgentRole.PORTFOLIO,
        settings=CFG.settings,
        risk_rules=CFG.risk_rules,
        _portfolio=Broken([]),
        clock=lambda: now,
    )
    report = run_agent(PortfolioAgent(), ctx, AnalysisRequest())
    assert report.status == AgentReportStatus.UNAVAILABLE
    assert report.verdict == AgentVerdict.NO_OPINION and "corrompu" in report.errors[0]


def test_context_enforces_permissions(now):
    ps, qs, _ = balanced(now)
    news_ctx = context(now, ps, [], qs, role=AgentRole.NEWS)
    with pytest.raises(PermissionDeniedError):
        _ = news_ctx.portfolio
    with pytest.raises(PermissionDeniedError):
        run_agent(PortfolioAgent(), news_ctx, AnalysisRequest())


def test_payload_is_json_and_journal_ready(now):
    import json

    ps, qs, _ = balanced(now)
    report = run_agent(PortfolioAgent(), context(now, ps, [cash(200)], qs), AnalysisRequest())
    json.dumps(report.payload)
    assert D(report.payload["total_value"]) == D("1400.00")


def test_stale_prices_flagged_in_report(now):
    ps, qs, hist = balanced(now)
    old = [quote(q.symbol, 100, now - timedelta(days=30)) for q in qs]
    report = run_agent(
        PortfolioAgent(), context(now, ps, [cash(200)], old, hist), AnalysisRequest()
    )
    assert report.payload["data_quality"] == "MEDIUM"
    assert all(
        "périmé" in p["issues"][0] for p in report.payload["positions"]
    )  # prix périmé signalé
