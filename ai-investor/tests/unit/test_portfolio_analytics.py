from datetime import timedelta
from decimal import Decimal as D

import pytest

from ai_investor.config import load_config
from ai_investor.core.enums import AssetType, QualityLevel
from ai_investor.portfolio.analytics import (
    CASH_BUCKET,
    DIVERSIFIED_BUCKET,
    UNKNOWN_BUCKET,
    analyze_portfolio,
)
from tests.helpers import bars, cash, position, quote

CFG = load_config()


def run(positions, cash_=(), quotes=None, histories=None, now=None, rules=None, **kw):
    from tests.conftest import NOW

    now = now or NOW
    return analyze_portfolio(
        positions,
        cash_,
        quotes or {},
        histories or {},
        "EUR",
        now,
        CFG.settings,
        rules or CFG.risk_rules,
        **kw,
    )


def codes(a):
    return {al.code for al in a.alerts}


def diversified(now, n=12):
    """n positions de même valeur (100 € chacune) + 10 % de liquidités."""
    ps = [position(f"S{i}", 1, 90, sector=f"Secteur{i}", region="Europe") for i in range(n)]
    qs = {p.asset.symbol: quote(p.asset.symbol, 100, now) for p in ps}
    return ps, qs


def test_valuation_weights_and_performance(now):
    ps, qs = diversified(now)
    a = run(ps, [cash(133.33)], qs)
    assert a.valuation_complete and a.total_value == D("1333.33")
    assert a.invested_value == D(1200) and a.cost_basis_total == D(1080)
    assert a.unrealized_pnl == D(120) and a.unrealized_pnl_percent == D("11.11")
    assert a.positions[0].weight_percent == D("7.50")
    assert a.cash_percent == D("10.00")
    assert a.effective_positions == D(12) and a.hhi == D("0.0833")
    assert a.data_quality == QualityLevel.MEDIUM  # pas d'historique -> volatilité non calculée
    assert codes(a) == set()


def test_missing_price_is_never_replaced(now):
    ps, qs = diversified(now, 3)
    qs["S1"] = None
    a = run(ps, [cash(100)], qs)
    assert a.total_value is None and not a.valuation_complete
    assert a.known_value == D(300)  # 2 positions + cash, S1 non valorisée
    s1 = next(p for p in a.positions if p.symbol == "S1")
    assert s1.market_value is None and s1.price is None  # PRU (90) jamais utilisé comme prix
    assert a.data_quality == QualityLevel.LOW
    assert any("S1" in m for m in a.missing_data)
    assert a.unrealized_pnl is None


def test_unavailable_reason_is_reported(now):
    ps, _ = diversified(now, 1)
    a = run(ps, [], {"S0": None}, unavailable={"S0": "source de prix indisponible"})
    assert "indisponible" in a.positions[0].issues[0]


def test_stale_price_degrades_quality(now):
    ps, qs = diversified(now, 12)
    qs["S0"] = quote("S0", 100, now - timedelta(days=10))
    a = run(ps, [cash(134)], qs)
    assert "périmé" in a.positions[0].issues[0]
    assert a.data_quality == QualityLevel.MEDIUM


def test_foreign_currency_not_converted(now):
    p = position("AAPL", 1, 100, currency="USD")
    a = run([p], [cash(50), cash(20, "USD")], {"AAPL": quote("AAPL", 150, now, "USD")})
    assert a.positions[0].market_value is None and "conversion" in a.positions[0].issues[0]
    assert any("USD" in m for m in a.missing_data)
    assert a.data_quality == QualityLevel.LOW


def test_quote_currency_mismatch(now):
    p = position("X", 1, 100)
    a = run([p], [], {"X": quote("X", 150, now, "USD")})
    assert a.positions[0].market_value is None


def test_concentrated_portfolio_alerts(now):
    ps = [position("BIG", 10, 100, sector="Tech"), position("SMALL", 1, 100, sector="Santé")]
    qs = {"BIG": quote("BIG", 100, now), "SMALL": quote("SMALL", 100, now)}
    a = run(ps, [cash(10)], qs)
    assert {"POSITION_TOO_LARGE", "SECTOR_TOO_LARGE", "LOW_CASH", "CONCENTRATED"} <= codes(a)
    assert a.largest_position == "BIG" and a.largest_position_percent == D("90.09")  # 1000 / 1110
    big = next(al for al in a.alerts if al.code == "POSITION_TOO_LARGE")
    assert big.symbol == "BIG" and big.severity == "HIGH"


def test_exposures(now):
    ps = [
        position("CW8", 1, 100, asset_type=AssetType.ETF, region="Monde"),
        position("AIR", 1, 100, sector="Industrie", region="Europe"),
        position("XX", 1, 100),
    ]
    qs = {s: quote(s, 100, now) for s in ("CW8", "AIR", "XX")}
    a = run(ps, [cash(100)], qs)
    assert a.sector_exposure == {
        DIVERSIFIED_BUCKET: D(25),
        "Industrie": D(25),
        UNKNOWN_BUCKET: D(25),
        CASH_BUCKET: D(25),
    }
    assert a.region_exposure["Inconnu"] == D(25)
    assert a.currency_exposure == {"EUR": D(100)}
    assert a.asset_type_exposure["ETF"] == D(25)
    assert any("Secteur inconnu" in m for m in a.missing_data)
    assert any("transparence" in h for h in a.assumptions)


def test_etf_overlap_detected(now):
    ps = [
        position("CW8", 1, 100, asset_type=AssetType.ETF, tracked_index="MSCI World"),
        position("EWLD", 1, 100, asset_type=AssetType.ETF, tracked_index="msci world "),
        position("SP5", 1, 100, asset_type=AssetType.ETF, tracked_index="S&P 500"),
    ]
    a = run(ps, [], {p.asset.symbol: quote(p.asset.symbol, 100, now) for p in ps})
    assert a.etf_overlaps == (("CW8", "EWLD"),) and "ETF_OVERLAP" in codes(a)


def test_disallowed_and_forbidden_assets_flagged(now):
    rules = CFG.risk_rules.model_copy(update={"FORBIDDEN_ASSETS": frozenset({"AIR"})})
    ps = [position("BTC", 1, 100, asset_type=AssetType.CRYPTO), position("AIR", 1, 100)]
    a = run(ps, [], {"BTC": quote("BTC", 1, now), "AIR": quote("AIR", 1, now)}, rules=rules)
    assert {"ASSET_TYPE_NOT_ALLOWED", "FORBIDDEN_ASSET_HELD"} <= codes(a)


def test_volatility_and_drawdown_known_values(now):
    # 26 jours : hausse de 100 à 120 puis chute à 90 -> drawdown max = 90/120 - 1 = -25 %
    closes = [*(100 + i for i in range(21)), 110, 100, 95, 92, 90]  # 100..120 puis baisse
    p = position("X", 10, 100, sector="Tech")
    hist = {"X": bars("X", closes, now.date())}
    a = run([p], [], {"X": quote("X", 90, now)}, hist)
    assert a.history_days == 26
    assert a.max_drawdown_percent == D("-25.00")
    assert a.current_drawdown_percent == D("-25.00")
    assert a.volatility_annual_percent is not None and a.volatility_annual_percent > 0
    assert "DRAWDOWN_EXCEEDED" in codes(a)
    assert any("quantités actuelles constantes" in h for h in a.assumptions)


def test_short_history_gives_no_volatility(now):
    p = position("X", 1, 100)
    a = run([p], [], {"X": quote("X", 100, now)}, {"X": bars("X", [100, 101, 102], now.date())})
    assert a.volatility_annual_percent is None and a.max_drawdown_percent is None
    assert any("Historique commun insuffisant" in m for m in a.missing_data)


def test_empty_portfolio(now):
    a = run([], [])
    assert a.data_quality == QualityLevel.LOW and a.total_value == D(0)
    assert a.hhi is None


@pytest.mark.parametrize("hist_len", [0, 1])
def test_no_crash_on_tiny_history(now, hist_len):
    p = position("X", 1, 100)
    closes = [100] * hist_len
    a = run([p], [], {"X": quote("X", 100, now)}, {"X": bars("X", closes, now.date())})
    assert a.positions[0].last_daily_move_percent is None


def test_correlation(now):
    base = [100 + (i % 5) * 2 + i * 0.5 for i in range(30)]
    ps = [
        position("A", 1, 100, sector="A"),
        position("B", 1, 100, sector="B"),
        position("C", 1, 100, sector="C"),
    ]
    hist = {
        "A": bars("A", base, now.date()),
        "B": bars("B", [x * 2 for x in base], now.date()),  # parfaitement corrélé à A
        "C": bars("C", [100 + (i % 2) * 3 for i in range(30)], now.date()),
    }
    qs = {s: quote(s, 100, now) for s in "ABC"}
    a = run(ps, [], qs, hist)
    by_pair = {(c.a, c.b): c for c in a.correlations}
    assert by_pair[("A", "B")].coefficient == pytest.approx(1.0)
    assert by_pair[("A", "B")].observations == 29
    assert abs(by_pair[("A", "C")].coefficient) < 0.8
    flagged = [al.message for al in a.alerts if al.code == "HIGH_CORRELATION"]
    assert len(flagged) == 1 and "A et B" in flagged[0]


def test_abnormal_move(now):
    ps = [position("A", 1, 100, sector="A"), position("B", 1, 100, sector="B")]
    hist = {
        "A": bars("A", [100, 101, 102], now.date()),
        "B": bars("B", [100, 100, 91], now.date()),
    }  # -9 % >= seuil de 8 %
    a = run(ps, [], {s: quote(s, 100, now) for s in "AB"}, hist)
    moves = {al.symbol for al in a.alerts if al.code == "ABNORMAL_MOVE"}
    assert moves == {"B"}
    assert next(p for p in a.positions if p.symbol == "B").last_daily_move_percent == D("-9.00")
