"""Mesures de rendement / risque historiques.

PERFORMANCE HISTORIQUE ≠ PERFORMANCE FUTURE
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from datetime import date

from ai_investor.quant.indicators import TRADING_DAYS, simple_returns


def total_return(values: Sequence[float]) -> float | None:
    if len(values) < 2 or values[0] <= 0:
        return None
    return values[-1] / values[0] - 1


def cagr(values: Sequence[float], days: int) -> float | None:
    """Taux de croissance annualisé sur `days` jours calendaires."""
    tr = total_return(values)
    if tr is None or days <= 0 or tr <= -1:
        return None
    return float((1 + tr) ** (365.25 / days) - 1)


def sharpe_ratio(returns: Sequence[float], risk_free_annual: float = 0.0) -> float | None:
    """Sharpe annualisé à partir de rendements journaliers. None si non défini."""
    if len(returns) < 2:
        return None
    rf_daily = (1 + risk_free_annual) ** (1 / TRADING_DAYS) - 1
    excess = [r - rf_daily for r in returns]
    sd = statistics.stdev(excess)
    if sd == 0:
        return None
    return float(statistics.fmean(excess) / sd * math.sqrt(TRADING_DAYS))


def beta(asset_returns: Sequence[float], benchmark_returns: Sequence[float]) -> float | None:
    if len(asset_returns) != len(benchmark_returns) or len(asset_returns) < 2:
        return None
    var = statistics.variance(benchmark_returns)
    if var == 0:
        return None
    return statistics.covariance(asset_returns, benchmark_returns) / var


def aligned_returns(
    a: Mapping[date, float], b: Mapping[date, float]
) -> tuple[list[float], list[float]]:
    """Rendements journaliers calculés sur les seules dates communes."""
    days = sorted(set(a) & set(b))
    return simple_returns([a[d] for d in days]), simple_returns([b[d] for d in days])


def correlation_matrix(
    series: Mapping[str, Mapping[date, float]], min_observations: int
) -> dict[str, dict[str, float | None]]:
    names = sorted(series)
    matrix: dict[str, dict[str, float | None]] = {n: {} for n in names}
    for i, x in enumerate(names):
        matrix[x][x] = 1.0
        for y in names[i + 1 :]:
            rx, ry = aligned_returns(series[x], series[y])
            value: float | None = None
            if len(rx) >= min_observations:
                try:
                    value = round(statistics.correlation(rx, ry), 4)
                except statistics.StatisticsError:
                    value = None
            matrix[x][y] = matrix[y][x] = value
    return matrix
