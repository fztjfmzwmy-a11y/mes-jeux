"""Indicateurs de base (fonctions pures). Aucune prévision : uniquement des mesures du passé.

PERFORMANCE HISTORIQUE ≠ PERFORMANCE FUTURE
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

TRADING_DAYS = 252
PCT = Decimal("0.01")


def to_pct(value: float) -> Decimal:
    return Decimal(value * 100).quantize(PCT)


def simple_returns(values: Sequence[float]) -> list[float]:
    """Rendements simples successifs ; les points non positifs sont ignorés comme base."""
    return [values[i] / values[i - 1] - 1 for i in range(1, len(values)) if values[i - 1] > 0]


def sma(values: Sequence[float], window: int) -> float | None:
    """Moyenne mobile simple des `window` dernières valeurs ; None si historique trop court."""
    if window <= 0 or len(values) < window:
        return None
    return sum(values[-window:]) / window


def annualized_volatility(returns: Sequence[float]) -> float | None:
    if len(returns) < 2:
        return None
    return statistics.stdev(returns) * math.sqrt(TRADING_DAYS)


@dataclass(frozen=True)
class Drawdown:
    maximum: float  # négatif ou nul (ex. -0.25 = -25 %)
    current: float
    peak_index: int
    trough_index: int


def drawdown(values: Sequence[float]) -> Drawdown | None:
    if not values:
        return None
    peak = values[0]
    peak_i = trough_i = 0
    worst = 0.0
    worst_peak_i = 0
    for i, v in enumerate(values):
        if v > peak:
            peak, peak_i = v, i
        dd = v / peak - 1 if peak > 0 else 0.0
        if dd < worst:
            worst, trough_i, worst_peak_i = dd, i, peak_i
    current = values[-1] / peak - 1 if peak > 0 else 0.0
    return Drawdown(maximum=worst, current=current, peak_index=worst_peak_i, trough_index=trough_i)


def value_on_or_before(series: Sequence[tuple[date, float]], target: date) -> float | None:
    """Dernière valeur connue à la date `target` ou avant (série triée par date)."""
    result = None
    for day, value in series:
        if day > target:
            break
        result = value
    return result


def period_return(series: Sequence[tuple[date, float]], start: date) -> float | None:
    """Rendement entre `start` (ou la dernière valeur avant) et la dernière valeur.

    None si l'historique ne remonte pas jusqu'à `start` : jamais d'extrapolation.
    """
    if not series or series[0][0] > start:
        return None
    base = value_on_or_before(series, start)
    if base is None or base <= 0:
        return None
    return series[-1][1] / base - 1
