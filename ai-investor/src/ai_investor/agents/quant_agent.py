"""AGENT QUANT — analyse quantitative (section 7).

Calcule, lorsque les données le permettent : rendement historique, CAGR, volatilité,
drawdown maximal, ratio de Sharpe, bêta et corrélation vs référence, moyennes mobiles,
variations, matrice de corrélations, scénarios Monte Carlo et backtests.

PERFORMANCE HISTORIQUE ≠ PERFORMANCE FUTURE — affiché dans chaque rapport.

Avis dans le vote (lecture statistique du passé, pas une prévision) :
- moins de QUANT_MIN_HISTORY_DAYS cours ou données douteuses -> NO_OPINION ;
- Sharpe historique >= seuil ET drawdown actuel moins sévère que MAX_DRAWDOWN -> BUY ;
- Sharpe historique < 0 -> WAIT ;
- sinon HOLD.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from ai_investor.agents.base import Agent, AgentContext, AnalysisRequest
from ai_investor.core.enums import AgentReportStatus, AgentVerdict, QualityLevel
from ai_investor.core.errors import ProviderUnavailableError
from ai_investor.core.models import AgentReport, DataReference, PriceBar
from ai_investor.data.validation import check_series
from ai_investor.portfolio.fees import FeeModel
from ai_investor.quant import backtest as bt
from ai_investor.quant.indicators import annualized_volatility, drawdown, simple_returns, sma
from ai_investor.quant.monte_carlo import simulate
from ai_investor.quant.risk_metrics import (
    aligned_returns,
    beta,
    cagr,
    correlation_matrix,
    sharpe_ratio,
    total_return,
)
from ai_investor.security.permissions import AgentRole

DISCLAIMER = "PERFORMANCE HISTORIQUE ≠ PERFORMANCE FUTURE"
DEFAULT_LOOKBACK_DAYS = 5 * 365
BACKTEST_CAPITAL = 10_000.0


def _r(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def _pct(value: float | None) -> str:
    return "n.d." if value is None else f"{value * 100:.2f} %"


class QuantAgent(Agent):
    role = AgentRole.QUANT

    def analyze(self, context: AgentContext, request: AnalysisRequest) -> AgentReport:
        if not request.subject:
            return self._insufficient(context, request, "aucun actif à analyser")
        market = context.market
        if market is None:
            return self._insufficient(context, request, "aucune source de marché configurée")
        s = context.settings
        symbol = request.subject.strip().upper()
        params = request.parameters
        now = context.now()
        lookback = int(params.get("lookback_days", DEFAULT_LOOKBACK_DAYS))
        start = (now - timedelta(days=lookback)).date()

        def history(sym: str) -> list[PriceBar]:
            return list(market.get_price_history(sym, start, now.date()))

        try:
            raw = history(symbol)
        except ProviderUnavailableError as exc:
            return self._insufficient(context, request, f"source de marché indisponible ({exc})")
        currency = str(params.get("currency") or (raw[-1].currency if raw else s.BASE_CURRENCY))
        check = check_series(
            raw, currency, now, s.OUTLIER_JUMP_PERCENT, s.MAX_HISTORY_GAP_DAYS, s.MAX_DATA_AGE_DAYS
        )
        bars = list(check.bars)
        missing: list[str] = []
        issues = [f"[{i.level}] {i.message}" for i in check.issues]
        if check.critical or len(bars) < s.QUANT_MIN_HISTORY_DAYS:
            if len(bars) < s.QUANT_MIN_HISTORY_DAYS:
                missing.append(
                    f"historique insuffisant ({len(bars)} cours, {s.QUANT_MIN_HISTORY_DAYS} requis)"
                )
            report = self._insufficient(
                context, request, "; ".join(missing + issues) or "données douteuses"
            )
            return report

        refs = [
            DataReference(
                description=f"historique {symbol} ({len(bars)} cours)", source=bars[-1].source
            )
        ]
        days = [b.day for b in bars]
        closes = [float(b.close) for b in bars]
        rets = simple_returns(closes)
        rf = float(s.RISK_FREE_RATE_PERCENT) / 100
        dd = drawdown(closes)
        metrics: dict[str, Any] = {
            "observations": len(bars),
            "start": days[0].isoformat(),
            "end": days[-1].isoformat(),
            "total_return": _r(total_return(closes)),
            "cagr": _r(cagr(closes, (days[-1] - days[0]).days)),
            "volatility": _r(annualized_volatility(rets)),
            "max_drawdown": _r(dd.maximum if dd else None),
            "current_drawdown": _r(dd.current if dd else None),
            "sharpe": _r(sharpe_ratio(rets, rf), 3),
            "risk_free_rate": rf,
            "moving_averages": {f"MM{n}": _r(sma(closes, n), 4) for n in (20, 50, 200)},
            "variations": {
                label: _r(closes[-1] / closes[-1 - n] - 1) if len(closes) > n else None
                for label, n in (("1J", 1), ("5J", 5), ("21J", 21))
            },
        }

        # Référence : bêta et corrélation.
        benchmark = params.get("benchmark") or s.MARKET_BENCHMARK_SYMBOL
        metrics["benchmark"] = None
        if benchmark and str(benchmark).upper() != symbol:
            bsym = str(benchmark).upper()
            try:
                bbars = [b for b in history(bsym) if b.currency == currency]
            except ProviderUnavailableError:
                bbars = []
            if len(bbars) > s.MIN_HISTORY_DAYS:
                ra, rb = aligned_returns(
                    {b.day: float(b.close) for b in bars}, {b.day: float(b.close) for b in bbars}
                )
                corr = correlation_matrix(
                    {
                        symbol: {b.day: float(b.close) for b in bars},
                        bsym: {b.day: float(b.close) for b in bbars},
                    },
                    s.MIN_HISTORY_DAYS,
                )
                metrics["benchmark"] = {
                    "symbol": bsym,
                    "observations": len(ra),
                    "beta": _r(beta(ra, rb), 3),
                    "correlation": corr[symbol][bsym],
                }
                refs.append(DataReference(description=f"référence {bsym}", source=bbars[-1].source))
            else:
                missing.append(f"référence {bsym} : historique indisponible ou insuffisant")
        else:
            missing.append("aucune référence : bêta non calculé")

        # Matrice de corrélations sur un univers facultatif.
        universe = [str(u).upper() for u in params.get("universe", []) if str(u).upper() != symbol]
        metrics["correlations"] = None
        if universe:
            series: dict[str, dict[Any, float]] = {symbol: {b.day: float(b.close) for b in bars}}
            for sym in universe:
                try:
                    series[sym] = {
                        b.day: float(b.close) for b in history(sym) if b.currency == currency
                    }
                except ProviderUnavailableError:
                    missing.append(f"{sym} : source indisponible")
            metrics["correlations"] = correlation_matrix(series, s.MIN_HISTORY_DAYS)

        # Monte Carlo.
        horizon = int(params.get("horizon_days", s.MONTE_CARLO_HORIZON_DAYS))
        mc = simulate(rets, horizon, s.MONTE_CARLO_PATHS, s.MONTE_CARLO_SEED)
        metrics["monte_carlo"] = {
            "paths": mc.paths,
            "horizon_days": mc.horizon_days,
            "seed": mc.seed,
            "sample_size": mc.sample_size,
            "percentiles": {k: _r(v) for k, v in mc.percentiles.items()},
            "probability_of_loss": _r(mc.probability_of_loss),
            "median_max_drawdown": _r(mc.median_max_drawdown),
            "max_drawdown_p95": _r(mc.worst_max_drawdown_p95),
            "assumptions": list(mc.assumptions),
        }

        # Backtests : Buy & Hold vs filtre de moyenne mobile.
        window = int(params.get("sma_window", 200))
        fees = FeeModel(fixed=s.SIMULATION_FEE_FIXED, percent=s.SIMULATION_FEE_PERCENT)
        results = [
            bt.run_backtest(days, closes, strat, BACKTEST_CAPITAL, fees, rf)
            for strat in (bt.BuyAndHold(), bt.MovingAverageFilter(window))
        ]
        metrics["backtests"] = [
            {
                "strategy": r.strategy,
                "total_return": _r(r.total_return),
                "cagr": _r(r.cagr),
                "volatility": _r(r.volatility),
                "max_drawdown": _r(r.max_drawdown),
                "sharpe": _r(r.sharpe, 3),
                "trades": r.trades,
                "fees_paid": round(r.fees_paid, 2),
                "exposure": _r(r.exposure),
            }
            for r in results
        ]
        metrics["warnings"] = list(bt.WARNINGS)

        quality = QualityLevel.MEDIUM if check.issues or missing else QualityLevel.HIGH
        metrics["data_quality"] = quality
        return self._report(context, symbol, metrics, issues, missing, tuple(refs))

    # --------------------------------------------------------------------------------

    def _insufficient(
        self, context: AgentContext, request: AnalysisRequest, reason: str
    ) -> AgentReport:
        return AgentReport(
            agent=self.role,
            created_at=context.now(),
            status=AgentReportStatus.INSUFFICIENT_DATA,
            subject=request.subject,
            summary=f"DONNÉES INSUFFISANTES : {reason}.",
            errors=(reason,),
            hypotheses=(DISCLAIMER,),
        )

    def _report(
        self,
        context: AgentContext,
        symbol: str,
        m: dict[str, Any],
        issues: list[str],
        missing: list[str],
        refs: tuple[DataReference, ...],
    ) -> AgentReport:
        s = context.settings
        facts = [
            f"Période : {m['start']} → {m['end']} ({m['observations']} cours)",
            f"Rendement total {_pct(m['total_return'])}, annualisé {_pct(m['cagr'])}",
            f"Volatilité annualisée {_pct(m['volatility'])}, drawdown max "
            f"{_pct(m['max_drawdown'])}, actuel {_pct(m['current_drawdown'])}",
            f"Sharpe historique {m['sharpe']} (taux sans risque supposé "
            f"{m['risk_free_rate'] * 100:.2f} %)",
            "Variations : " + ", ".join(f"{k} {_pct(v)}" for k, v in m["variations"].items()),
        ]
        if m["benchmark"]:
            b = m["benchmark"]
            facts.append(
                f"Bêta vs {b['symbol']} : {b['beta']}, corrélation {b['correlation']} "
                f"({b['observations']} jours)"
            )
        mc = m["monte_carlo"]
        p = mc["percentiles"]
        facts.append(
            f"Monte Carlo ({mc['paths']} scénarios, {mc['horizon_days']} j, graine {mc['seed']}) :"
            f" P5 {_pct(p['P5'])}, médiane {_pct(p['P50'])}, P95 {_pct(p['P95'])}, "
            f"perte dans {_pct(mc['probability_of_loss'])} des scénarios"
        )
        for r in m["backtests"]:
            facts.append(
                f"Backtest {r['strategy']} : {_pct(r['total_return'])}, drawdown "
                f"{_pct(r['max_drawdown'])}, {r['trades']} opération(s), frais "
                f"{r['fees_paid']}"
            )

        interpretations = []
        sharpe = m["sharpe"]
        if sharpe is not None:
            interpretations.append(
                "Rendement ajusté du risque historiquement "
                + ("élevé" if sharpe >= 1 else "positif" if sharpe > 0 else "négatif")
                + f" (Sharpe {sharpe})"
            )
        if m["benchmark"] and m["benchmark"]["beta"] is not None:
            beta_v = m["benchmark"]["beta"]
            interpretations.append(
                f"Sensibilité {'supérieure' if beta_v > 1 else 'inférieure'} au marché de "
                f"référence (bêta {beta_v})"
            )
        bh, flt = m["backtests"]
        if bh["max_drawdown"] is not None and flt["max_drawdown"] is not None:
            if flt["max_drawdown"] == bh["max_drawdown"]:
                effect = "eu le même drawdown que le"
            elif flt["max_drawdown"] > bh["max_drawdown"]:
                effect = "limité le drawdown par rapport au"
            else:
                effect = "aggravé le drawdown par rapport au"
            interpretations.append(
                f"Sur cette période, le {flt['strategy']} aurait {effect} Buy & Hold "
                "— sans garantie pour l'avenir"
            )

        hypotheses = [DISCLAIMER, *bt.WARNINGS[1:], *mc["assumptions"]]

        risks = list(issues)
        if m["max_drawdown"] is not None and abs(m["max_drawdown"]) * 100 > float(
            context.risk_rules.MAX_DRAWDOWN
        ):
            risks.append(
                f"Drawdown historique {_pct(m['max_drawdown'])} au-delà de votre limite "
                f"de {context.risk_rules.MAX_DRAWDOWN} %"
            )
        if mc["probability_of_loss"] is not None and mc["probability_of_loss"] > 0.3:
            risks.append(f"Perte dans {_pct(mc['probability_of_loss'])} des scénarios simulés")

        current_dd = m["current_drawdown"]
        dd_ok = current_dd is None or abs(current_dd) * 100 <= float(
            context.risk_rules.MAX_DRAWDOWN
        )
        if sharpe is None:
            verdict = AgentVerdict.NO_OPINION
        elif Decimal(str(sharpe)) >= s.QUANT_SHARPE_BUY_THRESHOLD and dd_ok:
            verdict = AgentVerdict.BUY
        elif sharpe < 0:
            verdict = AgentVerdict.WAIT
        else:
            verdict = AgentVerdict.HOLD

        return AgentReport(
            agent=self.role,
            created_at=context.now(),
            status=AgentReportStatus.OK,
            verdict=verdict,
            subject=symbol,
            summary=f"{symbol} : lecture statistique du passé (Sharpe {sharpe}). {DISCLAIMER}.",
            facts=tuple(facts),
            interpretations=tuple(interpretations),
            hypotheses=tuple(hypotheses),
            risks=tuple(risks),
            data_used=refs,
            errors=tuple(missing),
            payload=m,
        )
