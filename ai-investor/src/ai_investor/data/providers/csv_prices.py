"""Historiques de prix depuis un fichier CSV fourni par l'utilisateur.

Colonnes : symbol, day (AAAA-MM-JJ), close, currency ; facultatives : open, high, low, volume.
Le dernier prix connu est le dernier cours de clôture, daté de la fin de sa journée (UTC) :
l'application ne suppose jamais un prix plus récent que ce que contient le fichier.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, date, datetime, time
from pathlib import Path

from pydantic import ValidationError

from ai_investor.core.enums import DataReliability
from ai_investor.core.models import PriceBar, Quote
from ai_investor.core.provenance import Source
from ai_investor.data.importers.positions import MAX_FILE_BYTES, PositionImportError, parse_decimal
from ai_investor.data.providers.memory import InMemoryMarketDataProvider
from ai_investor.security.secrets_guard import assert_no_sensitive_columns

REQUIRED = ("symbol", "day", "close", "currency")
OPTIONAL = ("open", "high", "low", "volume")


def parse_price_csv(content: str, source: Source) -> list[PriceBar]:
    if len(content.encode("utf-8")) > MAX_FILE_BYTES * 20:
        raise PositionImportError(["fichier de prix trop volumineux"])
    content = content.lstrip("﻿")
    first = content.splitlines()[0] if content else ""
    delimiter = ";" if first.count(";") > first.count(",") else ","
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    header = [h.strip().lower() for h in (reader.fieldnames or [])]
    assert_no_sensitive_columns(header)
    missing = [c for c in REQUIRED if c not in header]
    unknown = [h for h in header if h not in REQUIRED + OPTIONAL]
    if missing or unknown:
        raise PositionImportError(
            [f"colonnes manquantes : {missing}" if missing else f"colonnes inconnues : {unknown}"]
        )
    reader.fieldnames = header
    bars: list[PriceBar] = []
    errors: list[str] = []
    seen: set[tuple[str, date]] = set()
    for line, row in enumerate(reader, start=2):
        try:
            data: dict[str, object] = {
                "symbol": (row["symbol"] or "").strip().upper(),
                "day": date.fromisoformat((row["day"] or "").strip()),
                "close": parse_decimal(row["close"] or ""),
                "currency": row["currency"],
                "source": source,
            }
            for key in ("open", "high", "low"):
                if (row.get(key) or "").strip():
                    data[key] = parse_decimal(row[key])
            if (row.get("volume") or "").strip():
                data["volume"] = int(parse_decimal(row["volume"]))
            bar = PriceBar.model_validate(data)
        except (ValueError, ValidationError) as exc:
            errors.append(f"ligne {line} : {exc}".splitlines()[0])
            continue
        if (bar.symbol, bar.day) in seen:
            errors.append(f"ligne {line} : doublon {bar.symbol} {bar.day}")
            continue
        seen.add((bar.symbol, bar.day))
        bars.append(bar)
    if errors:
        raise PositionImportError(errors)
    return bars


class CsvMarketDataProvider(InMemoryMarketDataProvider):
    def __init__(self, path: Path) -> None:
        source = Source(
            name=f"fichier:{path.name}",
            reliability=DataReliability.USER_PROVIDED,
            reference=path.name,
        )
        bars = parse_price_csv(path.read_text(encoding="utf-8-sig"), source)
        latest: dict[str, PriceBar] = {}
        for bar in bars:
            if bar.symbol not in latest or bar.day > latest[bar.symbol].day:
                latest[bar.symbol] = bar
        quotes = [
            Quote(
                symbol=b.symbol,
                price=b.close,
                currency=b.currency,
                as_of=datetime.combine(b.day, time(23, 59), tzinfo=UTC),
                source=source,
            )
            for b in latest.values()
        ]
        super().__init__(quotes, bars, name=source.name, reliability=DataReliability.USER_PROVIDED)
