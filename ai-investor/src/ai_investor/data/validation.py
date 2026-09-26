"""Contrôle de qualité des séries de prix : prix aberrants, trous, incohérences.

Aucune donnée n'est corrigée ni supprimée : les problèmes sont SIGNALÉS et font baisser
la qualité des données. C'est à l'analyse de décider si elle peut conclure.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from ai_investor.core.models import PriceBar, Quote


class IssueLevel(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"  # la donnée reste exploitable avec prudence
    CRITICAL = "CRITICAL"  # pas de conclusion possible sur la donnée concernée


@dataclass(frozen=True)
class DataIssue:
    level: IssueLevel
    code: str
    message: str
    day: date | None = None


@dataclass(frozen=True)
class SeriesCheck:
    bars: tuple[PriceBar, ...]  # barres retenues (triées, bonne devise, sans doublon)
    issues: tuple[DataIssue, ...]

    @property
    def critical(self) -> bool:
        return any(i.level == IssueLevel.CRITICAL for i in self.issues)


def check_series(
    bars: Sequence[PriceBar],
    currency: str,
    now: datetime,
    jump_percent: Decimal,
    max_gap_days: int,
    max_age_days: int,
) -> SeriesCheck:
    issues: list[DataIssue] = []
    other = [b for b in bars if b.currency != currency]
    if other:
        issues.append(
            DataIssue(
                IssueLevel.WARNING,
                "CURRENCY_MIX",
                f"{len(other)} cours dans une autre devise ignorés",
            )
        )
    kept: dict[date, PriceBar] = {}
    for bar in sorted((b for b in bars if b.currency == currency), key=lambda b: b.day):
        if bar.day in kept:
            if kept[bar.day].close != bar.close:
                issues.append(
                    DataIssue(
                        IssueLevel.WARNING,
                        "CONFLICTING_DUPLICATE",
                        f"deux cours différents le {bar.day}",
                        bar.day,
                    )
                )
            continue
        kept[bar.day] = bar
    series = tuple(kept.values())
    future = [b for b in series if b.day > now.date()]
    if future:
        issues.append(
            DataIssue(
                IssueLevel.CRITICAL,
                "FUTURE_DATE",
                f"cours daté dans le futur ({future[0].day})",
                future[0].day,
            )
        )
        series = tuple(b for b in series if b.day <= now.date())
    if not series:
        issues.append(DataIssue(IssueLevel.CRITICAL, "NO_DATA", "aucun cours disponible"))
        return SeriesCheck((), tuple(issues))

    age = (now.date() - series[-1].day).days
    if age > max_age_days:
        issues.append(
            DataIssue(
                IssueLevel.WARNING,
                "STALE",
                f"dernier cours du {series[-1].day} ({age} jours)",
                series[-1].day,
            )
        )

    limit = jump_percent / 100
    closes = [b.close for b in series]
    skip_next = False
    for i in range(1, len(series)):
        gap = (series[i].day - series[i - 1].day).days
        if gap > max_gap_days:
            issues.append(
                DataIssue(
                    IssueLevel.WARNING,
                    "GAP",
                    f"trou de {gap} jours avant le {series[i].day}",
                    series[i].day,
                )
            )
        move = closes[i] / closes[i - 1] - 1
        if skip_next:  # retour d'un pic déjà signalé
            skip_next = False
            continue
        if abs(move) < limit:
            continue
        if i + 1 < len(series):
            back = closes[i + 1] / closes[i] - 1
            reverted = back * move < 0 and abs(back) >= abs(move) / 2
            if reverted:
                skip_next = True
                issues.append(
                    DataIssue(
                        IssueLevel.WARNING,
                        "SPIKE",
                        f"prix aberrant probable le {series[i].day} "
                        f"({move * 100:+.1f} % puis {back * 100:+.1f} %)",
                        series[i].day,
                    )
                )
            else:
                issues.append(
                    DataIssue(
                        IssueLevel.WARNING,
                        "JUMP",
                        f"variation extrême le {series[i].day} ({move * 100:+.1f} %)"
                        " : division d'actions, erreur ou événement réel ?",
                        series[i].day,
                    )
                )
        else:
            issues.append(
                DataIssue(
                    IssueLevel.CRITICAL,
                    "UNCONFIRMED_LAST_JUMP",
                    f"dernier cours en variation extrême ({move * 100:+.1f} %) non confirmée",
                    series[i].day,
                )
            )
    return SeriesCheck(series, tuple(issues))


def check_quote(quote: Quote, last_close: Decimal | None, jump_percent: Decimal) -> list[DataIssue]:
    """Compare le dernier prix au dernier cours de clôture connu."""
    if last_close is None or last_close <= 0:
        return []
    gap = quote.price / last_close - 1
    if abs(gap) >= jump_percent / 100:
        return [
            DataIssue(
                IssueLevel.CRITICAL,
                "QUOTE_OUTLIER",
                f"prix {quote.price} éloigné de {gap * 100:+.1f} % du dernier cours ({last_close})",
            )
        ]
    return []
