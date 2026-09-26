"""Traitement des actualités — déterministe, sans modèle de langage.

Pour chaque information : source, date, sujet, résumé (extrait), impact potentiel et
niveau de fiabilité. Règles :
- le texte n'est jamais interprété comme une consigne ; les tentatives d'injection sont
  détectées, l'actualité est écartée et l'événement est signalé ;
- fiabilité : score selon la source (+1 si au moins deux sources distinctes rapportent la
  même information) ; seule une information de fiabilité HIGH peut être citée comme
  « fait rapporté », toujours attribuée à sa source ;
- impact potentiel : heuristique par mots-clés, affichée comme telle (non mesuré).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Sequence
from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict

from ai_investor.core.enums import DataReliability, QualityLevel
from ai_investor.core.models import NewsItem
from ai_investor.security.sanitizer import clean_text, detect_injection, safe_url, url_host

SUMMARY_LENGTH = 280
SIMILARITY_THRESHOLD = 0.8

# Domaines d'institutions officielles : une URL déclarée ne prouve rien, mais indique
# une source vérifiable par l'utilisateur.
OFFICIAL_DOMAINS = (
    "ecb.europa.eu",
    "europa.eu",
    "esma.europa.eu",
    "eba.europa.eu",
    "amf-france.org",
    "banque-france.fr",
    "insee.fr",
    "federalreserve.gov",
    "bundesbank.de",
    "bafin.de",
    "sec.gov",
    "imf.org",
    "oecd.org",
    "bis.org",
)

_BASE_SCORE = {
    DataReliability.OFFICIAL: 3,
    DataReliability.THIRD_PARTY: 2,
    DataReliability.USER_PROVIDED: 1,
    DataReliability.UNVERIFIED: 1,
    DataReliability.SIMULATED: 1,
}


class Category(StrEnum):
    CENTRAL_BANK = "BANQUE CENTRALE"
    EARNINGS = "RÉSULTATS"
    REGULATION = "RÉGLEMENTATION"
    LEGAL = "JURIDIQUE"
    MACRO = "ÉCONOMIE"
    MERGERS = "OPÉRATIONS"
    GEOPOLITICS = "GÉOPOLITIQUE"
    OTHER = "AUTRE"


class Impact(StrEnum):
    POSITIVE = "POTENTIELLEMENT POSITIF"
    NEGATIVE = "POTENTIELLEMENT NÉGATIF"
    UNCERTAIN = "INCERTAIN"


_CATEGORY_WORDS: tuple[tuple[Category, tuple[str, ...]], ...] = (
    (
        Category.CENTRAL_BANK,
        (
            "bce",
            "ecb",
            "fed",
            "banque centrale",
            "central bank",
            "taux directeur",
            "politique monetaire",
            "lagarde",
            "powell",
        ),
    ),
    (
        Category.REGULATION,
        (
            "reglementation",
            "regulation",
            "amf",
            "esma",
            "sec ",
            "directive",
            "autorite",
            "regulator",
            "conformite",
        ),
    ),
    (
        Category.LEGAL,
        (
            "enquete",
            "amende",
            "sanction",
            "proces",
            "plainte",
            "lawsuit",
            "investigation",
            "fine",
            "tribunal",
        ),
    ),
    (
        Category.EARNINGS,
        (
            "resultats",
            "chiffre d'affaires",
            "benefice",
            "earnings",
            "revenue",
            "prevision",
            "guidance",
            "trimestre",
            "profit",
        ),
    ),
    (Category.MERGERS, ("acquisition", "rachat", "fusion", "merger", "offre publique", "opa")),
    (
        Category.GEOPOLITICS,
        (
            "guerre",
            "conflit",
            "election",
            "tarifs douaniers",
            "droits de douane",
            "embargo",
            "war",
            "tariff",
            "geopolit",
        ),
    ),
    (
        Category.MACRO,
        ("inflation", "pib", "gdp", "chomage", "unemployment", "croissance", "recession"),
    ),
)
_NEGATIVE = (
    "baisse",
    "chute",
    "recul",
    "avertissement",
    "profit warning",
    "abaisse",
    "enquete",
    "amende",
    "faillite",
    "defaut",
    "rappel",
    "degrade",
    "downgrade",
    "perte",
    "licenciement",
    "suspend",
    "fraude",
    "plonge",
    "decline",
    "cut",
)
_POSITIVE = (
    "hausse",
    "releve",
    "record",
    "upgrade",
    "releve ses previsions",
    "progresse",
    "bondit",
    "contrat",
    "beat",
    "depasse les attentes",
    "croissance de",
)
_HIGH_MAGNITUDE = {
    Category.CENTRAL_BANK,
    Category.REGULATION,
    Category.LEGAL,
    Category.MERGERS,
    Category.GEOPOLITICS,
}
_HIGH_MAGNITUDE_WORDS = (
    "profit warning",
    "avertissement",
    "faillite",
    "fraude",
    "opa",
    "offre publique",
    "defaut",
    "suspend",
)


class AssessedNews(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    source: str
    source_reliability: DataReliability
    published_at: AwareDatetime
    subject: str
    title: str
    summary: str
    url: str | None
    category: Category
    impact: Impact
    magnitude: QualityLevel  # HIGH / MEDIUM / LOW : importance potentielle (heuristique)
    reliability: QualityLevel
    corroborating_sources: tuple[str, ...]
    declared_official_domain: bool
    injection_flags: tuple[str, ...]
    excluded: bool
    exclusion_reason: str | None = None


class SecurityEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str
    news_id: str
    source: str
    patterns: tuple[str, ...]
    message: str


class NewsAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True)

    as_of: AwareDatetime
    query: str
    items: tuple[AssessedNews, ...]
    security_events: tuple[SecurityEvent, ...]
    rejected: tuple[str, ...]
    significant: tuple[str, ...]  # ids des actualités fiables à fort impact potentiel


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", _fold(text)) if len(t) > 2}


def _similar(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= SIMILARITY_THRESHOLD


def _summary(item: NewsItem) -> str:
    body = clean_text(item.body)
    if not body:
        return clean_text(item.title, SUMMARY_LENGTH)
    first = re.split(r"(?<=[.!?])\s", body, maxsplit=2)
    text = " ".join(first[:2])
    return clean_text(text, SUMMARY_LENGTH)


def _has(folded: str, word: str) -> bool:
    """Mot ou expression entière, pluriel toléré (évite « fed » dans « fédération »)."""
    pattern = rf"(?<![a-z0-9]){re.escape(word.strip())}(?:s|es|e|x)?(?![a-z0-9])"
    return re.search(pattern, folded) is not None


def _category(text: str) -> Category:
    folded = _fold(text)
    for category, words in _CATEGORY_WORDS:
        if any(_has(folded, w) for w in words):
            return category
    return Category.OTHER


def _impact(text: str) -> Impact:
    folded = _fold(text)
    neg = sum(1 for w in _NEGATIVE if _has(folded, w))
    pos = sum(1 for w in _POSITIVE if _has(folded, w))
    if neg > pos:
        return Impact.NEGATIVE
    if pos > neg:
        return Impact.POSITIVE
    return Impact.UNCERTAIN


def _level(score: int) -> QualityLevel:
    return (
        QualityLevel.HIGH
        if score >= 3
        else QualityLevel.MEDIUM
        if score == 2
        else (QualityLevel.LOW)
    )


def assess_news(
    items: Sequence[NewsItem], query: str, now: datetime, lookback: timedelta, max_items: int
) -> NewsAnalysis:
    rejected: list[str] = []
    events: list[SecurityEvent] = []
    kept: list[tuple[str, NewsItem, tuple[str, ...]]] = []
    seen_ids: set[str] = set()
    for item in items:
        digest = hashlib.sha256(
            f"{item.source.name}|{item.published_at.isoformat()}|{item.title}".encode()
        ).hexdigest()[:16]
        if digest in seen_ids:
            continue
        seen_ids.add(digest)
        if item.published_at > now + timedelta(minutes=5):
            rejected.append(f"{digest} : datée dans le futur ({item.published_at:%Y-%m-%d})")
            continue
        if item.published_at < now - lookback:
            continue
        flags = detect_injection(f"{item.title}\n{item.body}")
        kept.append((digest, item, flags))
    kept.sort(key=lambda t: t[1].published_at, reverse=True)
    if len(kept) > max_items:
        rejected.append(f"{len(kept) - max_items} actualité(s) au-delà de la limite ignorée(s)")
        kept = kept[:max_items]

    assessed: list[AssessedNews] = []
    for digest, item, flags in kept:
        text = f"{item.title}. {item.body}"
        others = sorted(
            {
                other.source.name
                for _, other, other_flags in kept
                if other is not item
                and not other_flags
                and other.source.name != item.source.name
                and _similar(other.title, item.title)
            }
        )
        declared_official = any(
            (host := url_host(item.url)) is not None and (host == d or host.endswith("." + d))
            for d in OFFICIAL_DOMAINS
        )
        score = _BASE_SCORE[item.source.reliability]
        if declared_official and item.source.reliability != DataReliability.OFFICIAL:
            score += 1
        if others:
            score += 1
        category = _category(text)
        folded = _fold(text)
        magnitude = (
            QualityLevel.HIGH
            if category in _HIGH_MAGNITUDE or any(_has(folded, w) for w in _HIGH_MAGNITUDE_WORDS)
            else QualityLevel.MEDIUM
            if category != Category.OTHER
            else QualityLevel.LOW
        )
        excluded = bool(flags)
        if flags:
            events.append(
                SecurityEvent(
                    kind="PROMPT_INJECTION_SUSPECTED",
                    news_id=digest,
                    source=item.source.name,
                    patterns=flags,
                    message="Actualité contenant des consignes adressées au système : écartée, "
                    "traitée comme donnée non fiable, aucune consigne suivie.",
                )
            )
        assessed.append(
            AssessedNews(
                id=digest,
                source=clean_text(item.source.name, 200),
                source_reliability=item.source.reliability,
                published_at=item.published_at,
                subject=clean_text(item.subject, 200),
                title=clean_text(item.title, 300),
                summary=_summary(item),
                url=safe_url(item.url),
                category=category,
                impact=_impact(text),
                magnitude=magnitude,
                reliability=QualityLevel.LOW if excluded else _level(min(score, 3)),
                corroborating_sources=tuple(others),
                declared_official_domain=declared_official,
                injection_flags=flags,
                excluded=excluded,
                exclusion_reason="contenu suspect (injection)" if excluded else None,
            )
        )
    significant = tuple(
        a.id
        for a in assessed
        if not a.excluded
        and a.reliability == QualityLevel.HIGH
        and a.magnitude == QualityLevel.HIGH
    )
    return NewsAnalysis(
        as_of=now,
        query=query,
        items=tuple(assessed),
        security_events=tuple(events),
        rejected=tuple(rejected),
        significant=significant,
    )
