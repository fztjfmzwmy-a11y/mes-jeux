"""Fournisseurs d'actualités : mémoire et fichier JSON importé par l'utilisateur.

JSON : [{"source": "...", "published_at": "2026-09-25T08:00:00+00:00", "subject": "...",
         "title": "...", "body": "...", "url": "https://...", "related_symbols": ["AIR"]}]

Une actualité importée est une donnée FOURNIE PAR L'UTILISATEUR : sa fiabilité est
USER_PROVIDED quelle que soit la source déclarée (qui ne peut pas être vérifiée ici).
Aucun accès réseau : les flux RSS / API d'actualités seront ajoutés plus tard.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from ai_investor.core.enums import DataReliability
from ai_investor.core.errors import ProviderUnavailableError
from ai_investor.core.models import NewsItem
from ai_investor.core.provenance import Source
from ai_investor.data.importers.positions import MAX_FILE_BYTES, PositionImportError
from ai_investor.data.interfaces import NewsDataProvider, ProviderInfo
from ai_investor.security.secrets_guard import assert_no_sensitive_fields

ALLOWED_KEYS = {"source", "published_at", "subject", "title", "body", "url", "related_symbols"}
MAX_ITEMS = 5000


class InMemoryNewsDataProvider(NewsDataProvider):
    def __init__(
        self,
        items: Iterable[NewsItem] = (),
        name: str = "actualites-memoire",
        reliability: DataReliability = DataReliability.SIMULATED,
        available: bool = True,
    ) -> None:
        self._items = sorted(items, key=lambda i: i.published_at)
        self._info = ProviderInfo(name=name, reliability=reliability)
        self.available = available

    @property
    def info(self) -> ProviderInfo:
        return self._info

    def get_news(self, query: str, since: datetime) -> Sequence[NewsItem]:
        if not self.available:
            raise ProviderUnavailableError(f"Fournisseur {self._info.name} indisponible")
        q = query.strip().lower()
        return [
            i
            for i in self._items
            if i.published_at >= since
            and (
                not q
                or q == i.subject.lower()
                or q in (s.lower() for s in i.related_symbols)
                or q in i.title.lower()
            )
        ]


def parse_news_json(content: str, file_name: str) -> list[NewsItem]:
    if len(content.encode("utf-8")) > MAX_FILE_BYTES * 5:
        raise PositionImportError(["fichier d'actualités trop volumineux"])
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise PositionImportError([f"JSON invalide (ligne {exc.lineno}) : {exc.msg}"]) from None
    if not isinstance(data, list):
        raise PositionImportError(["une liste d'actualités est attendue"])
    if len(data) > MAX_ITEMS:
        raise PositionImportError([f"trop d'actualités (> {MAX_ITEMS})"])
    assert_no_sensitive_fields(data)
    items: list[NewsItem] = []
    errors: list[str] = []
    for index, raw in enumerate(data):
        label = f"actualité[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{label} : objet attendu")
            continue
        extra = sorted(set(raw) - ALLOWED_KEYS)
        if extra:
            errors.append(f"{label} : champ(s) inconnu(s) : {', '.join(extra)}")
            continue
        try:
            source = Source(
                name=str(raw.get("source") or "").strip() or "source inconnue",
                reliability=DataReliability.USER_PROVIDED,
                reference=file_name,
            )
            items.append(
                NewsItem(
                    source=source,
                    published_at=datetime.fromisoformat(str(raw["published_at"])),
                    subject=str(raw.get("subject") or ""),
                    title=str(raw.get("title") or ""),
                    body=str(raw.get("body") or ""),
                    url=raw.get("url"),
                    related_symbols=tuple(str(s).upper() for s in raw.get("related_symbols") or ()),
                )
            )
        except (KeyError, ValueError, TypeError, ValidationError) as exc:
            errors.append(f"{label} : {str(exc).splitlines()[0]}")
    if errors:
        raise PositionImportError(errors)
    return items


class JsonNewsDataProvider(InMemoryNewsDataProvider):
    def __init__(self, path: Path) -> None:
        super().__init__(
            parse_news_json(path.read_text(encoding="utf-8-sig"), path.name),
            name=f"fichier:{path.name}",
            reliability=DataReliability.USER_PROVIDED,
        )
