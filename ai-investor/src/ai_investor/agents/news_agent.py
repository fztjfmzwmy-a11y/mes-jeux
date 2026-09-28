"""AGENT NEWS — actualités récentes (section 6).

Pour chaque information : source, date, sujet, résumé, impact potentiel, fiabilité.

- Une information n'est citée comme « fait rapporté » que si sa fiabilité est HIGH, et
  toujours attribuée à sa source (« Selon X… ») ; sinon elle est rangée parmi les
  informations NON VÉRIFIÉES (hypothèses).
- Le contenu des actualités n'est JAMAIS traité comme une instruction. Les tentatives
  d'injection sont écartées et remontées dans `payload.security_events` pour journalisation.
- L'impact est une heuristique par mots-clés, affichée comme telle.

Avis dans le vote : le News Agent ne recommande jamais d'acheter ou de vendre.
- au moins une information fiable (HIGH) à fort impact potentiel -> REVIEW_REQUIRED
  (un événement significatif impose de réexaminer la décision) ;
- sinon NO_OPINION.
"""

from __future__ import annotations

from datetime import timedelta

from ai_investor.agents.base import Agent, AgentContext, AnalysisRequest
from ai_investor.core.enums import AgentReportStatus, AgentVerdict, QualityLevel
from ai_investor.core.errors import ProviderUnavailableError
from ai_investor.core.models import AgentReport, DataReference
from ai_investor.core.provenance import Source
from ai_investor.news.analysis import NewsAnalysis, assess_news
from ai_investor.security.permissions import AgentRole

MAX_LISTED = 10
HEURISTIC_NOTE = "impact estimé par mots-clés, non mesuré"


class NewsAgent(Agent):
    role = AgentRole.NEWS

    def analyze(self, context: AgentContext, request: AnalysisRequest) -> AgentReport:
        provider = context.news
        if provider is None:
            return self._insufficient(context, request, "aucune source d'actualités configurée")
        s = context.settings
        now = context.now()
        if "query" in request.parameters:
            query = str(request.parameters["query"] or "")
        else:
            query = request.subject or ""
        lookback = timedelta(days=s.NEWS_LOOKBACK_DAYS)
        try:
            items = provider.get_news(query, now - lookback)
        except ProviderUnavailableError as exc:
            return self._insufficient(context, request, f"source d'actualités indisponible ({exc})")
        analysis = assess_news(items, query, now, lookback, s.NEWS_MAX_ITEMS)
        ref = DataReference(
            description=f"actualités « {query or 'toutes'} » ({len(analysis.items)} retenues)",
            source=Source(name=provider.info.name, reliability=provider.info.reliability),
            as_of=now,
        )
        return self._report(context, request, analysis, (ref,))

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
        a: NewsAnalysis,
        refs: tuple[DataReference, ...],
    ) -> AgentReport:
        usable = [i for i in a.items if not i.excluded]
        facts: list[str] = []
        interpretations: list[str] = []
        unverified: list[str] = []
        for item in usable[:MAX_LISTED]:
            line = f"{item.source} ({item.published_at:%Y-%m-%d}) : {item.title}"
            if item.reliability == QualityLevel.HIGH:
                facts.append(f"Selon {line}")
            else:
                unverified.append(
                    f"Information NON VÉRIFIÉE (fiabilité {item.reliability}) — {line}"
                )
            interpretations.append(
                f"{item.title[:80]} : {item.impact}, catégorie {item.category}, importance "
                f"potentielle {item.magnitude} ({HEURISTIC_NOTE})"
            )
        if not usable:
            facts.append(
                f"Aucune actualité exploitable sur les {context.settings.NEWS_LOOKBACK_DAYS}"
                " derniers jours dans la source consultée"
            )

        risks = [
            f"Événement significatif : {i.title} ({i.source}, {i.published_at:%Y-%m-%d}) — "
            f"{i.impact}"
            for i in usable
            if i.id in a.significant
        ]
        risks += [
            f"[SÉCURITÉ] {e.message} Source : {e.source} ; motifs : {', '.join(e.patterns)}"
            for e in a.security_events
        ]

        verdict = AgentVerdict.REVIEW_REQUIRED if a.significant else AgentVerdict.NO_OPINION
        summary = (
            f"{len(usable)} actualité(s) exploitable(s), {len(a.significant)} significative(s), "
            f"{len(a.security_events)} écartée(s) pour contenu suspect."
        )
        return AgentReport(
            agent=self.role,
            created_at=context.now(),
            status=AgentReportStatus.OK,
            verdict=verdict,
            subject=request.subject,
            summary=summary,
            facts=tuple(facts),
            interpretations=tuple(interpretations),
            hypotheses=tuple(unverified),
            risks=tuple(risks),
            data_used=refs,
            errors=a.rejected,
            payload=a.model_dump(mode="json"),
        )
