"""AGENT MACRO — environnement macroéconomique et scénarios (section 5).

Toujours trois scénarios : CENTRAL, FAVORABLE, DÉFAVORABLE, sans probabilité.
Ne prétend jamais connaître l'avenir.

Avis dans le vote : le Macro Agent ne justifie jamais un achat à lui seul.
- données insuffisantes -> NO_OPINION ;
- au moins deux signaux de tension (courbe inversée, contraction, chômage en hausse,
  inflation élevée + resserrement) -> WAIT ;
- sinon HOLD.
L'environnement géopolitique n'est pas mesuré ici (pas de donnée structurée) : il relève
de l'agent News.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from ai_investor.agents.base import Agent, AgentContext, AnalysisRequest
from ai_investor.core.enums import AgentReportStatus, AgentVerdict, QualityLevel
from ai_investor.core.errors import ProviderUnavailableError
from ai_investor.core.models import AgentReport, DataReference, MacroObservation
from ai_investor.core.provenance import Source
from ai_investor.macro.analysis import (
    DEFAULT_INDICATORS,
    NO_PROBABILITY,
    Category,
    IndicatorSpec,
    MacroAnalysis,
    analyze_macro,
)
from ai_investor.security.permissions import AgentRole

LOOKBACK_DAYS = 3 * 365
STRESS_WAIT_THRESHOLD = 2


def _specs(overrides: Any) -> tuple[IndicatorSpec, ...]:
    """Permet de remplacer les codes (ex. {"INFLATION": "FR_CPI_YOY"}) sans changer les règles."""
    if not isinstance(overrides, dict):
        return DEFAULT_INDICATORS
    specs = []
    for spec in DEFAULT_INDICATORS:
        code = overrides.get(spec.category.value)
        specs.append(
            IndicatorSpec(spec.category, str(code).upper(), spec.label, spec.stale_after_days)
            if code
            else spec
        )
    return tuple(specs)


class MacroAgent(Agent):
    role = AgentRole.MACRO

    def analyze(self, context: AgentContext, request: AnalysisRequest) -> AgentReport:
        now = context.now()
        s = context.settings
        specs = _specs(request.parameters.get("indicators"))
        provider = context.macro
        series: dict[Category, list[MacroObservation]] = {}
        unavailable: dict[Category, str] = {}
        start = (now - timedelta(days=LOOKBACK_DAYS)).date()
        for spec in specs:
            if provider is None:
                unavailable[spec.category] = "aucune source macro configurée"
                continue
            try:
                series[spec.category] = list(provider.get_indicator(spec.code, start, now.date()))
            except ProviderUnavailableError as exc:
                unavailable[spec.category] = f"source indisponible ({exc})"
        exposures = request.parameters.get("exposures")
        analysis = analyze_macro(
            series,
            specs,
            now,
            s.MACRO_INFLATION_TARGET_PERCENT,
            s.MACRO_STABLE_THRESHOLD,
            exposures if isinstance(exposures, dict) else None,
            unavailable,
        )
        refs = tuple(
            DataReference(
                description=f"{r.label} ({r.code}), {r.observations} observations",
                source=_source(series, r.category),
                as_of=None,
            )
            for r in analysis.readings
        )
        return self._report(context, request, analysis, refs)

    def _report(
        self,
        context: AgentContext,
        request: AnalysisRequest,
        a: MacroAnalysis,
        refs: tuple[DataReference, ...],
    ) -> AgentReport:
        facts = []
        for r in a.readings:
            change = f", {r.change_12m:+} pt sur 12 mois" if r.change_12m is not None else ""
            facts.append(f"{r.label} : {r.value} {r.unit} ({r.period}, {r.source}){change}")
        interpretations = [f"{sig.name} : {sig.value} — règle : {sig.rule}" for sig in a.signals]
        hypotheses = [NO_PROBABILITY]
        for sc in a.scenarios:
            hypotheses.append(f"SCÉNARIO {sc.kind} — {sc.title} : {sc.narrative}")
        hypotheses.append("Environnement géopolitique non mesuré ici (voir agent News).")
        risks = [f"Signal de tension : {sig.name} ({sig.value})" for sig in a.signals if sig.stress]
        adverse = a.scenarios[2]
        risks.append(
            f"Scénario défavorable à surveiller : {adverse.title} "
            f"(signes : {', '.join(adverse.conditions)})"
        )

        insufficient = a.data_quality == QualityLevel.LOW
        if insufficient:
            verdict = AgentVerdict.NO_OPINION
        elif a.stress_count >= STRESS_WAIT_THRESHOLD:
            verdict = AgentVerdict.WAIT
        else:
            verdict = AgentVerdict.HOLD
        summary = (
            "DONNÉES INSUFFISANTES : trois scénarios génériques présentés."
            if insufficient
            else f"{len(a.readings)} indicateurs lus, {a.stress_count} signal(aux) de tension. "
            "Trois scénarios présentés, sans probabilité."
        )
        return AgentReport(
            agent=self.role,
            created_at=context.now(),
            status=AgentReportStatus.INSUFFICIENT_DATA if insufficient else AgentReportStatus.OK,
            verdict=verdict,
            subject=request.subject,
            summary=summary,
            facts=tuple(facts),
            interpretations=tuple(interpretations),
            hypotheses=tuple(hypotheses),
            risks=tuple(risks),
            data_used=refs,
            errors=a.missing,
            payload=a.model_dump(mode="json"),
        )


def _source(series: dict[Category, list[MacroObservation]], category: Category) -> Source:
    return series[category][-1].source
