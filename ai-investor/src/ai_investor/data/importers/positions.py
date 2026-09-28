"""Import manuel de positions depuis un fichier CSV ou JSON fourni par l'utilisateur.

Règles :
- le fichier est une DONNÉE : son contenu n'est jamais interprété comme une instruction ;
- tout champ ressemblant à un identifiant (mot de passe, PIN, token, IBAN…) fait
  refuser l'import entier, avant tout traitement, sans recopier la valeur ;
- import « tout ou rien » : une seule ligne invalide fait refuser le fichier, avec la
  liste précise des erreurs (numéro de ligne, champ, raison) ;
- aucune valeur manquante n'est complétée ou devinée.

Colonnes CSV (séparateur `,` `;` ou tabulation, en-tête obligatoire) :
  obligatoires : symbol, name, asset_type, currency, quantity, average_price
  facultatives : isin, sector, region, country, tracked_index
Décimales : `12.5` ou `12,5` (virgule décimale) ; `1 234,56` et `1.234,56` acceptés.
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ai_investor.core.errors import AIInvestorError
from ai_investor.core.models import Asset, CashBalance, Position
from ai_investor.security.secrets_guard import (
    assert_no_sensitive_columns,
    assert_no_sensitive_fields,
)

MAX_FILE_BYTES = 1_000_000
MAX_ROWS = 2_000
REQUIRED_COLUMNS = ("symbol", "name", "asset_type", "currency", "quantity", "average_price")
OPTIONAL_COLUMNS = ("isin", "sector", "region", "country", "tracked_index")
ASSET_FIELDS = ("symbol", "name", "asset_type", "currency", *OPTIONAL_COLUMNS)


class PositionImportError(AIInvestorError):
    """Fichier refusé ; `errors` détaille chaque problème."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("Import refusé :\n- " + "\n- ".join(errors))


@dataclass(frozen=True)
class ImportResult:
    positions: tuple[Position, ...]
    cash: tuple[CashBalance, ...]
    source_name: str


_NUMBER_RE = re.compile(r"^[+-]?[0-9][0-9 .,  ']*$")


def parse_decimal(raw: str) -> Decimal:
    text = raw.strip().replace(" ", "").replace(" ", "").replace(" ", "").replace("'", "")
    if not text or not _NUMBER_RE.match(text):
        raise ValueError(f"nombre invalide : {raw!r}")
    if "," in text and "." in text:
        decimal_sep = "," if text.rfind(",") > text.rfind(".") else "."
        thousands = "." if decimal_sep == "," else ","
        text = text.replace(thousands, "").replace(decimal_sep, ".")
    elif "," in text:
        if text.count(",") > 1:
            raise ValueError(f"nombre ambigu : {raw!r}")
        text = text.replace(",", ".")
    elif text.count(".") > 1:
        raise ValueError(f"nombre ambigu : {raw!r}")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"nombre invalide : {raw!r}") from None
    if not value.is_finite():
        raise ValueError(f"nombre invalide : {raw!r}")
    return value


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_position(row: dict[str, Any], label: str, errors: list[str]) -> Position | None:
    missing = [c for c in REQUIRED_COLUMNS if _clean(row.get(c)) is None]
    if missing:
        errors.append(f"{label} : champ(s) obligatoire(s) vide(s) : {', '.join(missing)}")
        return None
    try:
        quantity = parse_decimal(str(row["quantity"]))
        average_price = parse_decimal(str(row["average_price"]))
    except ValueError as exc:
        errors.append(f"{label} : {exc}")
        return None
    asset_data = {k: _clean(row.get(k)) for k in ASSET_FIELDS}
    asset_data["asset_type"] = (asset_data["asset_type"] or "").upper()
    try:
        asset = Asset.model_validate(asset_data)
        return Position(asset=asset, quantity=quantity, average_price=average_price)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        errors.append(f"{label} : {details}")
        return None


def _finalize(
    positions: list[Position], cash: list[CashBalance], errors: list[str], source_name: str
) -> ImportResult:
    keys = [p.asset.key for p in positions]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    if duplicates:
        errors.append(f"positions en double : {', '.join(duplicates)}")
    if not positions and not cash:
        errors.append("aucune position ni liquidité trouvée")
    if errors:
        raise PositionImportError(errors)
    return ImportResult(tuple(positions), tuple(cash), source_name)


def _check_size(content: str) -> None:
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise PositionImportError([f"fichier trop volumineux (> {MAX_FILE_BYTES} octets)"])


def parse_positions_csv(content: str, source_name: str = "import.csv") -> ImportResult:
    _check_size(content)
    content = content.lstrip("﻿")  # BOM ajouté par certains tableurs
    try:
        dialect = csv.Sniffer().sniff(content.splitlines()[0] if content else "", ",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    header = [h.strip().lower() for h in (reader.fieldnames or [])]
    assert_no_sensitive_columns(header)
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise PositionImportError([f"colonne(s) manquante(s) : {', '.join(missing)}"])
    unknown = [h for h in header if h not in REQUIRED_COLUMNS + OPTIONAL_COLUMNS]
    if unknown:
        raise PositionImportError([f"colonne(s) inconnue(s) : {', '.join(unknown)}"])
    reader.fieldnames = header

    positions: list[Position] = []
    errors: list[str] = []
    for index, row in enumerate(reader, start=2):
        if index - 1 > MAX_ROWS:
            raise PositionImportError([f"trop de lignes (> {MAX_ROWS})"])
        if None in row:  # plus de valeurs que de colonnes
            errors.append(f"ligne {index} : nombre de colonnes incorrect")
            continue
        if all(_clean(v) is None for v in row.values()):
            continue
        position = _build_position(row, f"ligne {index}", errors)
        if position is not None:
            positions.append(position)
    return _finalize(positions, [], errors, source_name)


def parse_positions_json(content: str, source_name: str = "import.json") -> ImportResult:
    """Format : {"positions": [{...}], "cash": [{"currency": "EUR", "amount": "1000"}]}"""
    _check_size(content)
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise PositionImportError([f"JSON invalide (ligne {exc.lineno}) : {exc.msg}"]) from None
    if not isinstance(data, dict):
        raise PositionImportError(["le JSON doit être un objet {positions, cash}"])
    assert_no_sensitive_fields(data)
    unknown = sorted(set(data) - {"positions", "cash"})
    if unknown:
        raise PositionImportError([f"clé(s) inconnue(s) : {', '.join(unknown)}"])
    raw_positions = data.get("positions", [])
    raw_cash = data.get("cash", [])
    if not isinstance(raw_positions, list) or not isinstance(raw_cash, list):
        raise PositionImportError(["'positions' et 'cash' doivent être des listes"])
    if len(raw_positions) > MAX_ROWS:
        raise PositionImportError([f"trop de positions (> {MAX_ROWS})"])

    errors: list[str] = []
    positions: list[Position] = []
    for index, item in enumerate(raw_positions):
        label = f"positions[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} : objet attendu")
            continue
        extra = sorted(set(item) - set(REQUIRED_COLUMNS + OPTIONAL_COLUMNS))
        if extra:
            errors.append(f"{label} : champ(s) inconnu(s) : {', '.join(extra)}")
            continue
        if any(isinstance(item.get(k), float) for k in ("quantity", "average_price")):
            errors.append(f'{label} : nombres à fournir en texte ("12.5") pour rester exacts')
            continue
        position = _build_position(item, label, errors)
        if position is not None:
            positions.append(position)

    cash: list[CashBalance] = []
    for index, item in enumerate(raw_cash):
        label = f"cash[{index}]"
        if not isinstance(item, dict) or set(item) != {"currency", "amount"}:
            errors.append(f"{label} : format attendu {{currency, amount}}")
            continue
        try:
            cash.append(
                CashBalance(
                    currency=str(item["currency"]), amount=parse_decimal(str(item["amount"]))
                )
            )
        except (ValueError, ValidationError) as exc:
            errors.append(f"{label} : {exc}")
    currencies = [c.currency for c in cash]
    if len(currencies) != len(set(currencies)):
        errors.append("plusieurs soldes de liquidités dans la même devise")
    return _finalize(positions, cash, errors, source_name)


def load_positions_file(path: Path) -> ImportResult:
    suffix = path.suffix.lower()
    if path.stat().st_size > MAX_FILE_BYTES:
        raise PositionImportError([f"fichier trop volumineux (> {MAX_FILE_BYTES} octets)"])
    content = path.read_text(encoding="utf-8-sig")
    if suffix == ".csv":
        return parse_positions_csv(content, path.name)
    if suffix == ".json":
        return parse_positions_json(content, path.name)
    raise PositionImportError([f"format non pris en charge : {suffix} (CSV ou JSON attendu)"])
