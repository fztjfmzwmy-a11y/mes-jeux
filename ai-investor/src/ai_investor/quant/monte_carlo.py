"""Simulation Monte Carlo par rééchantillonnage des rendements historiques (bootstrap).

HYPOTHÈSES (affichées avec chaque résultat) :
- les rendements futurs ressemblent aux rendements journaliers passés ;
- ils sont tirés indépendamment les uns des autres (pas de mémoire, pas de régime de crise
  prolongé autre que ceux présents dans l'échantillon) ;
- aucun événement absent de l'historique n'est simulé.
Le résultat est une FOURCHETTE de scénarios, pas une prévision.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

ASSUMPTIONS = (
    "Rendements futurs supposés semblables aux rendements journaliers passés (bootstrap).",
    "Tirages indépendants : les enchaînements de crise sont probablement sous-estimés.",
    "Aucun événement absent de l'historique n'est simulé.",
)


@dataclass(frozen=True)
class MonteCarloResult:
    paths: int
    horizon_days: int
    seed: int
    sample_size: int
    percentiles: dict[str, float]  # rendement final : P5, P25, P50, P75, P95
    probability_of_loss: float
    median_max_drawdown: float
    worst_max_drawdown_p95: float  # 95 % des scénarios ont un drawdown moins sévère
    assumptions: tuple[str, ...] = ASSUMPTIONS


def _quantile(sorted_values: Sequence[float], q: float) -> float:
    if not sorted_values:
        raise ValueError("échantillon vide")
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def simulate(
    daily_returns: Sequence[float], horizon_days: int, paths: int, seed: int
) -> MonteCarloResult:
    if len(daily_returns) < 2:
        raise ValueError("au moins deux rendements sont nécessaires")
    if horizon_days <= 0 or paths <= 0:
        raise ValueError("horizon et nombre de scénarios doivent être positifs")
    rng = random.Random(seed)  # noqa: S311 — simulation reproductible, pas de cryptographie
    finals: list[float] = []
    drawdowns: list[float] = []
    sample = list(daily_returns)
    for _ in range(paths):
        value = peak = 1.0
        worst = 0.0
        for r in rng.choices(sample, k=horizon_days):
            value *= 1 + r
            peak = max(peak, value)
            worst = min(worst, value / peak - 1)
        finals.append(value - 1)
        drawdowns.append(worst)
    finals.sort()
    drawdowns.sort()
    return MonteCarloResult(
        paths=paths,
        horizon_days=horizon_days,
        seed=seed,
        sample_size=len(sample),
        percentiles={
            f"P{int(q * 100)}": _quantile(finals, q) for q in (0.05, 0.25, 0.5, 0.75, 0.95)
        },
        probability_of_loss=sum(1 for f in finals if f < 0) / paths,
        median_max_drawdown=_quantile(drawdowns, 0.5),
        worst_max_drawdown_p95=_quantile(drawdowns, 0.05),
    )
