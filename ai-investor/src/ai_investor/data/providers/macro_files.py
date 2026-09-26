"""Fournisseurs d'indicateurs macroéconomiques : mémoire et fichier CSV.

CSV : code, label, period (AAAA-MM-JJ), value, unit ; colonne facultative `source`
(ex. « BCE », « Eurostat ») recopiée telle quelle comme nom de source.
Des connecteurs vers des API officielles (BCE, Eurostat, FRED) pourront implémenter la
même interface plus tard.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from ai_investor.core.enums import DataReliability
from ai_investor.core.errors import ProviderUnavailableError
from ai_investor.core.models import MacroObservation
from ai_investor.core.provenance import Source
from ai_investor.data.importers.positions import MAX_FILE_BYTES, PositionImportError, parse_decimal
from ai_investor.data.interfaces import MacroDataProvider, ProviderInfo
from ai_investor.security.secrets_guard import assert_no_sensitive_columns

REQUIRED = ("code", "label", "period", "value", "unit")
OPTIONAL = ("source",)


class InMemoryMacroDataProvider(MacroDataProvider):
    def __init__(
        self,
        observations: Iterable[MacroObservation] = (),
        name: str = "macro-memoire",
        reliability: DataReliability = DataReliability.SIMULATED,
        available: bool = True,
    ) -> None:
        self._data: dict[str, list[MacroObservation]] = {}
        for obs in observations:
            self._data.setdefault(obs.code.upper(), []).append(obs)
        for series in self._data.values():
            series.sort(key=lambda o: o.period)
        self._info = ProviderInfo(name=name, reliability=reliability)
        self.available = available

    @property
    def info(self) -> ProviderInfo:
        return self._info

    def get_indicator(self, code: str, start: date, end: date) -> Sequence[MacroObservation]:
        if not self.available:
            raise ProviderUnavailableError(f"Fournisseur {self._info.name} indisponible")
        return [o for o in self._data.get(code.upper(), []) if start <= o.period <= end]


def parse_macro_csv(content: str, file_name: str) -> list[MacroObservation]:
    if len(content.encode("utf-8")) > MAX_FILE_BYTES * 5:
        raise PositionImportError(["fichier macro trop volumineux"])
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
    out: list[MacroObservation] = []
    errors: list[str] = []
    seen: set[tuple[str, date]] = set()
    for line, row in enumerate(reader, start=2):
        try:
            source_name = (row.get("source") or "").strip() or f"fichier:{file_name}"
            obs = MacroObservation(
                code=(row["code"] or "").strip().upper(),
                label=(row["label"] or "").strip(),
                period=date.fromisoformat((row["period"] or "").strip()),
                value=parse_decimal(row["value"] or ""),
                unit=(row["unit"] or "").strip(),
                source=Source(
                    name=source_name, reliability=DataReliability.USER_PROVIDED, reference=file_name
                ),
            )
        except (ValueError, ValidationError) as exc:
            errors.append(f"ligne {line} : {str(exc).splitlines()[0]}")
            continue
        if (obs.code, obs.period) in seen:
            errors.append(f"ligne {line} : doublon {obs.code} {obs.period}")
            continue
        seen.add((obs.code, obs.period))
        out.append(obs)
    if errors:
        raise PositionImportError(errors)
    return out


class CsvMacroDataProvider(InMemoryMacroDataProvider):
    def __init__(self, path: Path) -> None:
        super().__init__(
            parse_macro_csv(path.read_text(encoding="utf-8-sig"), path.name),
            name=f"fichier:{path.name}",
            reliability=DataReliability.USER_PROVIDED,
        )
