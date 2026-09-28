"""Backtests simples, SANS BIAIS D'ANTICIPATION.

Garanties :
- la stratégie ne reçoit que les cours STRICTEMENT antérieurs au jour de décision
  (le moteur lui passe une copie tronquée : elle ne peut pas voir le futur) ;
- la position décidée au jour t est appliquée au cours de clôture du jour t
  (décision prise sur la clôture de t-1, exécutée à t) ;
- frais appliqués à chaque changement de position ;
- le capital non investi ne rapporte rien (hypothèse prudente, affichée).

Un backtest ne prouve RIEN sur l'avenir : PERFORMANCE HISTORIQUE ≠ PERFORMANCE FUTURE.
Il est aussi exposé à la sur-optimisation : tester beaucoup de paramètres et garder le
meilleur produit un résultat trompeur.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import pairwise

from ai_investor.portfolio.fees import FeeModel
from ai_investor.quant.indicators import annualized_volatility, drawdown, simple_returns, sma
from ai_investor.quant.risk_metrics import cagr, sharpe_ratio, total_return

WARNINGS = (
    "PERFORMANCE HISTORIQUE ≠ PERFORMANCE FUTURE",
    "Un backtest ne prouve pas qu'une stratégie fonctionnera dans le futur.",
    "Risque de sur-optimisation si les paramètres ont été choisis après coup.",
    "Liquidités non rémunérées ; pas de fiscalité ; exécution supposée au cours de clôture.",
)


class Strategy(ABC):
    name: str

    @abstractmethod
    def target_exposure(self, past_closes: Sequence[float]) -> float:
        """Exposition souhaitée (0 = liquidités, 1 = investi) à partir du passé uniquement."""


class BuyAndHold(Strategy):
    name = "Buy & Hold"

    def target_exposure(self, past_closes: Sequence[float]) -> float:
        return 1.0


class MovingAverageFilter(Strategy):
    """Investi si la dernière clôture connue est au-dessus de sa moyenne mobile."""

    def __init__(self, window: int = 200) -> None:
        if window < 2:
            raise ValueError("fenêtre trop courte")
        self.window = window
        self.name = f"Filtre MM{window}"

    def target_exposure(self, past_closes: Sequence[float]) -> float:
        average = sma(past_closes, self.window)
        if average is None:
            return 0.0  # pas assez d'historique : on ne suppose rien, on reste en liquidités
        return 1.0 if past_closes[-1] > average else 0.0


@dataclass(frozen=True)
class BacktestResult:
    strategy: str
    start: date
    end: date
    initial_capital: float
    final_value: float
    total_return: float | None
    cagr: float | None
    volatility: float | None
    max_drawdown: float | None
    sharpe: float | None
    trades: int
    fees_paid: float
    exposure: float  # part du temps investi
    equity: tuple[float, ...]
    warnings: tuple[str, ...] = WARNINGS


def run_backtest(
    days: Sequence[date],
    closes: Sequence[float],
    strategy: Strategy,
    initial_capital: float,
    fees: FeeModel,
    risk_free_annual: float = 0.0,
) -> BacktestResult:
    if len(days) != len(closes) or len(closes) < 2:
        raise ValueError("séries de dates et de cours incohérentes ou trop courtes")
    if any(later <= earlier for earlier, later in pairwise(days)):
        raise ValueError("les dates doivent être strictement croissantes")
    cash, units = initial_capital, 0.0
    equity: list[float] = [initial_capital]
    trades = 0
    fees_paid = 0.0
    invested_days = 0
    current = 0.0
    for t in range(1, len(closes)):
        past = tuple(closes[:t])  # uniquement jusqu'à t-1 inclus
        target = 1.0 if strategy.target_exposure(past) >= 0.5 else 0.0
        price = closes[t]
        if target != current:
            if target == 1.0:
                fee = float(fees.fee_for(Decimal(str(cash))))
                if cash > fee:
                    units = (cash - fee) / price
                    cash = 0.0
                    fees_paid += fee
                    trades += 1
                    current = 1.0
            else:
                gross = units * price
                fee = min(float(fees.fee_for(Decimal(str(gross)))), gross)
                cash = gross - fee
                units = 0.0
                fees_paid += fee
                trades += 1
                current = 0.0
        if current:
            invested_days += 1
        equity.append(cash + units * price)
    rets = simple_returns(equity)
    dd = drawdown(equity)
    return BacktestResult(
        strategy=strategy.name,
        start=days[0],
        end=days[-1],
        initial_capital=initial_capital,
        final_value=equity[-1],
        total_return=total_return(equity),
        cagr=cagr(equity, (days[-1] - days[0]).days),
        volatility=annualized_volatility(rets),
        max_drawdown=dd.maximum if dd else None,
        sharpe=sharpe_ratio(rets, risk_free_annual),
        trades=trades,
        fees_paid=fees_paid,
        exposure=invested_days / (len(closes) - 1),
        equity=tuple(equity),
    )
