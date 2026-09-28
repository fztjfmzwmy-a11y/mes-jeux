"""AGENT MARKET — analyse de marché d'un actif (section 4).

Sépare strictement :
- FACTS           : mesures issues des données (prix, performances, moyennes mobiles…) ;
- INTERPRETATIONS : lecture de ces mesures selon des règles explicites et affichées ;
- HYPOTHESES      : ce qui pourrait se passer — jamais présenté comme certain.

Règles de lecture (transparentes, non prédictives) :
- tendance HAUSSIÈRE : prix > MM200 et MM50 > MM200 ; BAISSIÈRE : prix < MM200 et MM50 < MM200 ;
  sinon SANS DIRECTION ; INCONNUE si moins de 200 cours ;
- momentum POSITIF : performances 3 et 6 mois > 0 ; NÉGATIF : les deux < 0 ; sinon MITIGÉ.

Avis dans le vote (signal technique, pas une recommandation) :
tendance haussière + momentum positif -> BUY ; tendance baissière + momentum négatif -> WAIT ;
tendance inconnue -> NO_OPINION ; sinon HOLD ; données insuffisantes -> NO_OPINION.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict

from ai_investor.agents.base import Agent, AgentContext, AnalysisRequest
from ai_investor.core.enums import AgentReportStatus, AgentVerdict, QualityLevel
from ai_investor.core.errors import ProviderUnavailableError
from ai_investor.core.models import AgentReport, DataReference, Fundamentals, PriceBar, Quote
from ai_investor.data.interfaces import MarketDataProvider
from ai_investor.data.validation import DataIssue, IssueLevel, check_quote, check_series
from ai_investor.quant.indicators import (
    annualized_volatility,
    drawdown,
    period_return,
    simple_returns,
    sma,
    to_pct,
)
from ai_investor.security.permissions import AgentRole

LOOKBACK_DAYS = 420
PERIODS = {"1M": 30, "3M": 91, "6M": 182, "1A": 365}
DISCLAIMER = "PERFORMANCE HISTORIQUE ≠ PERFORMANCE FUTURE"
FUNDAMENTALS_MAX_AGE_DAYS = 180


class Trend(StrEnum):
    UP = "HAUSSIÈRE"
    DOWN = "BAISSIÈRE"
    SIDEWAYS = "SANS DIRECTION"
    UNKNOWN = "INCONNUE"


class Momentum(StrEnum):
    POSITIVE = "POSITIF"
    NEGATIVE = "NÉGATIF"
    MIXED = "MITIGÉ"
    UNKNOWN = "INCONNU"


class Issue(BaseModel):
    model_config = ConfigDict(frozen=True)
    level: str
    code: str
    message: str


class ReferenceComparison(BaseModel):
    model_config = ConfigDict(frozen=True)
    symbol: str
    role: str  # "indice de référence" / "référence sectorielle"
    returns: dict[str, Decimal | None]
    relative: dict[str, Decimal | None]  # écart de performance en points de %
    volatility_1y_percent: Decimal | None


class MarketAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    as_of: AwareDatetime
    currency: str
    last_price: Decimal | None
    last_price_as_of: date | None
    last_price_source: str | None
    history_days: int
    first_day: date | None
    last_day: date | None
    returns: dict[str, Decimal | None]
    sma50: Decimal | None
    sma200: Decimal | None
    price_vs_sma200_percent: Decimal | None
    trend: Trend
    momentum: Momentum
    volatility_1y_percent: Decimal | None
    max_drawdown_1y_percent: Decimal | None
    current_drawdown_percent: Decimal | None
    adjusted_prices: bool
    references: tuple[ReferenceComparison, ...]
    sector: str | None
    valuation: dict[str, Any] | None
    issues: tuple[Issue, ...]
    missing_data: tuple[str, ...]
    data_quality: QualityLevel


def _dec(value: float | None, places: str = "0.01") -> Decimal | None:
    return None if value is None else Decimal(value).quantize(Decimal(places))


def _returns_by_period(series: list[tuple[date, float]], today: date) -> dict[str, Decimal | None]:
    out: dict[str, Decimal | None] = {}
    for label, days in PERIODS.items():
        r = period_return(series, today - timedelta(days=days))
        out[label] = to_pct(r) if r is not None else None
    return out


class MarketAgent(Agent):
    role = AgentRole.MARKET

    def analyze(self, context: AgentContext, request: AnalysisRequest) -> AgentReport:
        if not request.subject:
            return self._insufficient(context, request, "aucun actif à analyser")
        market = context.market
        if market is None:
            return self._insufficient(context, request, "aucune source de marché configurée")
        symbol = request.subject.strip().upper()
        now = context.now()
        params = request.parameters
        try:
            quote = market.get_latest_price(symbol)
            raw_bars = list(
                market.get_price_history(
                    symbol, (now - timedelta(days=LOOKBACK_DAYS)).date(), now.date()
                )
            )
            fundamentals = market.get_fundamentals(symbol)
        except ProviderUnavailableError as exc:
            return self._insufficient(context, request, f"source de marché indisponible ({exc})")

        currency = str(
            params.get("currency")
            or (quote.currency if quote else None)
            or (raw_bars[-1].currency if raw_bars else context.settings.BASE_CURRENCY)
        )
        analysis, refs = self._analyze(
            context, market, symbol, currency, quote, raw_bars, fundamentals, params, now
        )
        return self._report(context, analysis, refs)

    # --------------------------------------------------------------------------------

    def _analyze(
        self,
        context: AgentContext,
        market: MarketDataProvider,
        symbol: str,
        currency: str,
        quote: Quote | None,
        raw_bars: list[PriceBar],
        fundamentals: Fundamentals | None,
        params: dict[str, Any],
        now: datetime,
    ) -> tuple[MarketAnalysis, tuple[DataReference, ...]]:
        s = context.settings
        missing: list[str] = []
        check = check_series(
            raw_bars,
            currency,
            now,
            s.OUTLIER_JUMP_PERCENT,
            s.MAX_HISTORY_GAP_DAYS,
            s.MAX_DATA_AGE_DAYS,
        )
        issues = list(check.issues)
        bars = list(check.bars)
        refs: list[DataReference] = []
        if bars:
            refs.append(
                DataReference(
                    description=f"historique {symbol} ({len(bars)} cours)",
                    source=bars[-1].source,
                    as_of=None,
                )
            )

        # Dernier prix : cotation si cohérente, sinon dernier cours de clôture.
        last_price: Decimal | None = None
        last_day: date | None = None
        last_source: str | None = None
        if quote is not None and quote.currency == currency:
            quote_issues = check_quote(
                quote, bars[-1].close if bars else None, s.OUTLIER_JUMP_PERCENT
            )
            issues.extend(quote_issues)
            if now - quote.as_of > timedelta(days=s.MAX_DATA_AGE_DAYS):
                issues.append(_issue_stale_quote(quote))
            last_price, last_day, last_source = quote.price, quote.as_of.date(), quote.source.name
            refs.append(
                DataReference(
                    description=f"dernier prix {symbol}", source=quote.source, as_of=quote.as_of
                )
            )
        elif bars:
            last_price, last_day, last_source = bars[-1].close, bars[-1].day, bars[-1].source.name
            if quote is not None:
                missing.append(f"cotation en {quote.currency} ignorée (actif en {currency})")
        else:
            missing.append("aucun prix disponible")

        series = [(b.day, float(b.close)) for b in bars]
        closes = [v for _, v in series]
        today = now.date()
        returns = _returns_by_period(series, today) if series else dict.fromkeys(PERIODS)
        for label, value in returns.items():
            if value is None:
                missing.append(f"performance {label} : historique trop court")

        sma50, sma200 = sma(closes, 50), sma(closes, 200)
        ref_price = float(last_price) if last_price is not None else None
        trend = Trend.UNKNOWN
        if sma50 is not None and sma200 is not None and ref_price is not None:
            if ref_price > sma200 and sma50 > sma200:
                trend = Trend.UP
            elif ref_price < sma200 and sma50 < sma200:
                trend = Trend.DOWN
            else:
                trend = Trend.SIDEWAYS
        else:
            missing.append("tendance longue (MM200) : moins de 200 cours")

        r3, r6 = returns.get("3M"), returns.get("6M")
        if r3 is None or r6 is None:
            momentum = Momentum.UNKNOWN
        elif r3 > 0 and r6 > 0:
            momentum = Momentum.POSITIVE
        elif r3 < 0 and r6 < 0:
            momentum = Momentum.NEGATIVE
        else:
            momentum = Momentum.MIXED

        year = [v for d, v in series if d >= today - timedelta(days=365)]
        vol = (
            annualized_volatility(simple_returns(year)) if len(year) > s.MIN_HISTORY_DAYS else None
        )
        if vol is None:
            missing.append("volatilité 1 an : historique insuffisant")
        dd = drawdown(year) if year else None

        references: list[ReferenceComparison] = []
        for role, key in (
            ("indice de référence", "benchmark"),
            ("référence sectorielle", "sector_benchmark"),
        ):
            ref_symbol = params.get(key) or (
                s.MARKET_BENCHMARK_SYMBOL if key == "benchmark" else None
            )
            if not ref_symbol or str(ref_symbol).upper() == symbol:
                if key == "benchmark":
                    missing.append("aucun indice de référence configuré")
                continue
            comparison = self._reference(
                market, str(ref_symbol).upper(), role, currency, returns, now, refs, missing
            )
            if comparison is not None:
                references.append(comparison)

        valuation = None
        if fundamentals is not None:
            valuation = {
                k: v
                for k, v in fundamentals.model_dump(mode="json").items()
                if k in ("price_earnings", "price_book", "dividend_yield_percent", "ev_ebitda")
                and v is not None
            } or None
            refs.append(
                DataReference(
                    description=f"valorisation {symbol}",
                    source=fundamentals.source,
                    as_of=fundamentals.as_of,
                )
            )
            if now - fundamentals.as_of > timedelta(days=FUNDAMENTALS_MAX_AGE_DAYS):
                missing.append(f"données de valorisation anciennes ({fundamentals.as_of:%Y-%m-%d})")
        if valuation is None:
            missing.append("valorisation : données non disponibles")

        enough = len(bars) > s.MIN_HISTORY_DAYS and last_price is not None
        if check.critical or any(i.level == IssueLevel.CRITICAL for i in issues) or not enough:
            quality = QualityLevel.LOW
            if not enough:
                missing.append(
                    f"historique insuffisant ({len(bars)} cours, {s.MIN_HISTORY_DAYS + 1} requis)"
                )
        elif issues or trend == Trend.UNKNOWN:
            quality = QualityLevel.MEDIUM
        else:
            quality = QualityLevel.HIGH

        analysis = MarketAnalysis(
            symbol=symbol,
            as_of=now,
            currency=currency,
            last_price=last_price,
            last_price_as_of=last_day,
            last_price_source=last_source,
            history_days=len(bars),
            first_day=bars[0].day if bars else None,
            last_day=bars[-1].day if bars else None,
            returns=returns,
            sma50=_dec(sma50, "0.0001"),
            sma200=_dec(sma200, "0.0001"),
            price_vs_sma200_percent=to_pct(ref_price / sma200 - 1)
            if ref_price is not None and sma200
            else None,
            trend=trend,
            momentum=momentum,
            volatility_1y_percent=to_pct(vol) if vol is not None else None,
            max_drawdown_1y_percent=to_pct(dd.maximum) if dd else None,
            current_drawdown_percent=to_pct(dd.current) if dd else None,
            adjusted_prices=bool(bars) and all(b.adjusted for b in bars),
            references=tuple(references),
            sector=str(params["sector"]) if params.get("sector") else None,
            valuation=valuation,
            issues=tuple(Issue(level=i.level, code=i.code, message=i.message) for i in issues),
            missing_data=tuple(missing),
            data_quality=quality,
        )
        return analysis, tuple(refs)

    def _reference(
        self,
        market: MarketDataProvider,
        ref_symbol: str,
        role: str,
        currency: str,
        asset_returns: dict[str, Decimal | None],
        now: datetime,
        refs: list[DataReference],
        missing: list[str],
    ) -> ReferenceComparison | None:
        try:
            bars = list(
                market.get_price_history(
                    ref_symbol, (now - timedelta(days=LOOKBACK_DAYS)).date(), now.date()
                )
            )
        except ProviderUnavailableError:
            missing.append(f"{role} {ref_symbol} : source indisponible")
            return None
        bars = [b for b in bars if b.currency == currency]
        if not bars:
            missing.append(f"{role} {ref_symbol} : aucun cours en {currency}")
            return None
        refs.append(DataReference(description=f"{role} {ref_symbol}", source=bars[-1].source))
        series = sorted((b.day, float(b.close)) for b in bars)
        returns = _returns_by_period(series, now.date())
        relative: dict[str, Decimal | None] = {}
        for k, v in returns.items():
            mine = asset_returns.get(k)
            relative[k] = mine - v if mine is not None and v is not None else None
        year = [v for d, v in series if d >= now.date() - timedelta(days=365)]
        vol = annualized_volatility(simple_returns(year))
        return ReferenceComparison(
            symbol=ref_symbol,
            role=role,
            returns=returns,
            relative=relative,
            volatility_1y_percent=to_pct(vol) if vol is not None else None,
        )

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
        )

    def _report(
        self, context: AgentContext, a: MarketAnalysis, refs: tuple[DataReference, ...]
    ) -> AgentReport:
        cur = a.currency
        facts: list[str] = []
        if a.last_price is not None:
            facts.append(
                f"Dernier prix : {a.last_price} {cur} ({a.last_price_as_of}, "
                f"source {a.last_price_source})"
            )
        facts.append(f"Historique : {a.history_days} cours ({a.first_day} → {a.last_day})")
        perf = ", ".join(f"{k} {v} %" for k, v in a.returns.items() if v is not None)
        if perf:
            facts.append(f"Performances : {perf}")
        if a.sma50 is not None:
            facts.append(
                f"MM50 : {a.sma50} {cur}"
                + (f", MM200 : {a.sma200} {cur}" if a.sma200 is not None else "")
            )
        if a.volatility_1y_percent is not None:
            facts.append(
                f"Volatilité annualisée 1 an : {a.volatility_1y_percent} %, "
                f"drawdown max 1 an : {a.max_drawdown_1y_percent} %, "
                f"actuel : {a.current_drawdown_percent} %"
            )
        for ref in a.references:
            ref_perf = ", ".join(f"{k} {v} %" for k, v in ref.returns.items() if v is not None)
            facts.append(f"{ref.role.capitalize()} {ref.symbol} : {ref_perf or 'n.d.'}")
        if a.valuation:
            facts.append(
                "Valorisation : " + ", ".join(f"{k} = {v}" for k, v in a.valuation.items())
            )

        interpretations: list[str] = []
        if a.trend != Trend.UNKNOWN:
            interpretations.append(
                f"Tendance {a.trend} selon la règle MM50/MM200 "
                f"(prix à {a.price_vs_sma200_percent} % de la MM200)"
            )
        else:
            interpretations.append("Tendance longue : JE NE SAIS PAS (moins de 200 cours)")
        if a.momentum != Momentum.UNKNOWN:
            interpretations.append(f"Momentum {a.momentum} (performances 3 et 6 mois)")
        for ref in a.references:
            rel = ref.relative.get("1A")
            if rel is None:
                rel = ref.relative.get("3M")
                horizon = "3 mois"
            else:
                horizon = "1 an"
            if rel is not None:
                word = "surperformance" if rel > 0 else "sous-performance"
                interpretations.append(
                    f"{word.capitalize()} de {abs(rel)} points vs "
                    f"{ref.role} {ref.symbol} sur {horizon}"
                )
            if ref.volatility_1y_percent is not None and a.volatility_1y_percent is not None:
                more = a.volatility_1y_percent > ref.volatility_1y_percent
                interpretations.append(
                    f"Volatilité {'supérieure' if more else 'inférieure'} à {ref.symbol} "
                    f"({a.volatility_1y_percent} % vs {ref.volatility_1y_percent} %)"
                )
        if a.sector:
            interpretations.append(f"Secteur indiqué : {a.sector}")

        hypotheses = [DISCLAIMER]
        if a.trend in (Trend.UP, Trend.DOWN):
            hypotheses.append(
                f"HYPOTHÈSE : la tendance {a.trend} pourrait se poursuivre ou s'inverser ; "
                "aucune règle technique ne permet de le savoir à l'avance."
            )
        if a.history_days and not a.adjusted_prices:
            hypotheses.append(
                "Cours non ajustés (dividendes, divisions) : une division d'actions "
                "peut apparaître à tort comme une chute."
            )

        risks = [f"[{i.level}] {i.message}" for i in a.issues]
        if a.trend == Trend.DOWN:
            risks.append("Tendance baissière en cours")
        if a.current_drawdown_percent is not None and a.current_drawdown_percent <= Decimal(-20):
            risks.append(f"Actif à {a.current_drawdown_percent} % de son plus haut sur 1 an")

        insufficient = a.data_quality == QualityLevel.LOW
        if insufficient or a.trend == Trend.UNKNOWN:
            verdict = AgentVerdict.NO_OPINION
        elif a.trend == Trend.UP and a.momentum == Momentum.POSITIVE:
            verdict = AgentVerdict.BUY
        elif a.trend == Trend.DOWN and a.momentum == Momentum.NEGATIVE:
            verdict = AgentVerdict.WAIT
        else:
            verdict = AgentVerdict.HOLD
        summary = (
            "DONNÉES INSUFFISANTES : "
            + (
                "; ".join(i.message for i in a.issues if i.level == IssueLevel.CRITICAL)
                or "historique ou prix manquant"
            )
            if insufficient
            else f"{a.symbol} : tendance {a.trend}, momentum {a.momentum} (signal technique, "
            "pas une recommandation)."
        )
        return AgentReport(
            agent=self.role,
            created_at=context.now(),
            status=AgentReportStatus.INSUFFICIENT_DATA if insufficient else AgentReportStatus.OK,
            verdict=verdict,
            subject=a.symbol,
            summary=summary,
            facts=tuple(facts),
            interpretations=tuple(interpretations),
            hypotheses=tuple(hypotheses),
            risks=tuple(risks),
            data_used=refs if refs else (),
            errors=a.missing_data,
            payload=a.model_dump(mode="json"),
        )


def _issue_stale_quote(quote: Quote) -> DataIssue:
    return DataIssue(
        IssueLevel.WARNING, "STALE_QUOTE", f"dernier prix daté du {quote.as_of:%Y-%m-%d}"
    )
