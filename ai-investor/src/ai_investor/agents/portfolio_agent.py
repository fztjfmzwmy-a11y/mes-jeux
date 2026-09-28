"""AGENT PORTFOLIO — analyse du portefeuille (section 3).

Ne prend aucune décision d'investissement : il décrit l'état du portefeuille, détecte
les déséquilibres et signale les données manquantes. Son avis dans le vote porte
uniquement sur l'actif demandé (`subject`) :
- position au-delà de la limite de poids -> REDUCE ;
- position détenue sans alerte bloquante  -> HOLD ;
- actif non détenu ou données insuffisantes -> NO_OPINION.
"""

from __future__ import annotations

from datetime import timedelta

from ai_investor.agents.base import Agent, AgentContext, AnalysisRequest
from ai_investor.core.enums import AgentReportStatus, AgentVerdict, QualityLevel
from ai_investor.core.errors import ProviderUnavailableError
from ai_investor.core.models import AgentReport, DataReference, PriceBar, Quote
from ai_investor.core.provenance import Source
from ai_investor.portfolio.analytics import PortfolioAnalysis, Severity, analyze_portfolio
from ai_investor.security.permissions import AgentRole

HISTORY_LOOKBACK_DAYS = 400


class PortfolioAgent(Agent):
    role = AgentRole.PORTFOLIO

    def analyze(self, context: AgentContext, request: AnalysisRequest) -> AgentReport:
        now = context.now()
        provider = context.portfolio
        if provider is None:
            return self._insufficient(context, request, "Aucune source de portefeuille configurée")
        positions = provider.get_positions()
        cash = provider.get_cash_balances()
        portfolio_source = Source(name=provider.info.name, reliability=provider.info.reliability)

        market = context.market
        quotes: dict[str, Quote | None] = {}
        histories: dict[str, list[PriceBar]] = {}
        unavailable: dict[str, str] = {}
        start = (now - timedelta(days=HISTORY_LOOKBACK_DAYS)).date()
        for position in positions:
            symbol = position.asset.symbol
            if market is None:
                quotes[symbol] = None
                unavailable[symbol] = "aucune source de prix configurée"
                continue
            try:
                quotes[symbol] = market.get_latest_price(symbol)
                histories[symbol] = list(market.get_price_history(symbol, start, now.date()))
            except ProviderUnavailableError as exc:
                quotes[symbol] = None
                unavailable[symbol] = f"source de prix indisponible ({exc})"

        analysis = analyze_portfolio(
            positions,
            cash,
            quotes,
            histories,
            context.settings.BASE_CURRENCY,
            now,
            context.settings,
            context.risk_rules,
            unavailable,
        )
        data_used = [
            DataReference(description="positions et liquidités", source=portfolio_source, as_of=now)
        ]
        data_used += [
            DataReference(description=f"prix {q.symbol}", source=q.source, as_of=q.as_of)
            for q in quotes.values()
            if q is not None
        ]
        return self._report(context, request, analysis, tuple(data_used))

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
        self,
        context: AgentContext,
        request: AnalysisRequest,
        a: PortfolioAnalysis,
        data_used: tuple[DataReference, ...],
    ) -> AgentReport:
        cur = a.base_currency
        facts: list[str] = []
        if a.total_value is not None:
            facts.append(f"Valeur totale : {a.total_value} {cur}")
        else:
            facts.append(
                f"Valeur totale INCONNUE (valeur partielle connue : {a.known_value} {cur})"
            )
        facts.append(
            f"Liquidités : {a.cash} {cur}"
            + (f" ({a.cash_percent} %)" if a.cash_percent is not None else "")
        )
        for p in a.positions:
            if p.market_value is None:
                facts.append(f"{p.symbol} : {p.quantity} titres, non valorisé ({p.issues[-1]})")
            else:
                facts.append(
                    f"{p.symbol} : {p.market_value} {cur} ({p.weight_percent} %), "
                    f"latent {p.unrealized_pnl} {cur} ({p.unrealized_pnl_percent} %)"
                )
        if a.unrealized_pnl is not None:
            facts.append(
                f"Performance latente globale : {a.unrealized_pnl} {cur} "
                f"({a.unrealized_pnl_percent} %)"
            )
        if a.volatility_annual_percent is not None:
            facts.append(
                f"Volatilité annualisée (reconstituée) : {a.volatility_annual_percent} %, "
                f"drawdown max {a.max_drawdown_percent} %, actuel {a.current_drawdown_percent} %"
            )

        interpretations: list[str] = []
        if a.effective_positions is not None:
            level = (
                "faible"
                if a.hhi is not None and a.hhi >= context.settings.CONCENTRATION_HHI_ALERT
                else "correcte"
            )
            interpretations.append(
                f"Diversification {level} : équivalent à {a.effective_positions} positions "
                f"de même poids (HHI {a.hhi})"
            )
        top_sector = next(iter(a.sector_exposure.items()), None)
        if top_sector:
            interpretations.append(
                f"Première exposition sectorielle : {top_sector[0]} ({top_sector[1]} %)"
            )

        risks = [f"[{al.severity}] {al.message}" for al in a.alerts]
        insufficient = a.data_quality == QualityLevel.LOW
        verdict = AgentVerdict.NO_OPINION
        subject = request.subject.upper() if request.subject else None
        if subject and not insufficient:
            held = any(p.symbol == subject for p in a.positions)
            too_large = any(
                al.code == "POSITION_TOO_LARGE" and al.symbol == subject for al in a.alerts
            )
            if too_large:
                verdict = AgentVerdict.REDUCE
            elif held:
                verdict = AgentVerdict.HOLD

        high = sum(1 for al in a.alerts if al.severity == Severity.HIGH)
        summary = (
            "DONNÉES INSUFFISANTES : valorisation incomplète."
            if insufficient
            else f"Portefeuille analysé : {len(a.positions)} positions, "
            f"{len(a.alerts)} alerte(s) dont {high} élevée(s)."
        )
        return AgentReport(
            agent=self.role,
            created_at=context.now(),
            status=AgentReportStatus.INSUFFICIENT_DATA if insufficient else AgentReportStatus.OK,
            verdict=verdict,
            subject=subject,
            summary=summary,
            facts=tuple(facts),
            interpretations=tuple(interpretations),
            hypotheses=a.assumptions,
            risks=tuple(risks),
            data_used=data_used,
            errors=a.missing_data,
            payload=a.model_dump(mode="json"),
        )
