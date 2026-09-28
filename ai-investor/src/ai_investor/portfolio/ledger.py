"""Comptabilité du portefeuille virtuel — fonctions pures, sans base de données.

L'état d'un portefeuille est entièrement déterminé par la suite de ses transactions :
`replay()` permet donc de recalculer l'état à tout moment et de vérifier la base.

Conventions :
- une seule devise (la devise de base) en V1 : pas de conversion inventée ;
- le prix de revient moyen (PRU) inclut les frais d'achat ;
- les montants de liquidités sont arrondis au centime (arrondi bancaire).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal

from ai_investor.core.enums import SimulatedOperation
from ai_investor.core.errors import SimulationError
from ai_investor.core.models import SimulatedTransaction
from ai_investor.core.money import CENT

PRICE_PRECISION = Decimal("0.00000001")
ZERO = Decimal("0")

Op = SimulatedOperation


@dataclass(frozen=True)
class Holding:
    quantity: Decimal
    average_price: Decimal  # frais d'achat inclus

    @property
    def cost_basis(self) -> Decimal:
        return self.quantity * self.average_price


@dataclass(frozen=True)
class LedgerState:
    currency: str
    cash: Decimal = ZERO
    holdings: dict[str, Holding] = field(default_factory=dict)
    last_timestamp: datetime | None = None  # date de la dernière transaction


def _cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_EVEN)


def apply(state: LedgerState, tx: SimulatedTransaction) -> tuple[LedgerState, Decimal | None]:
    """Applique une transaction. Retourne le nouvel état et la plus-value réalisée éventuelle.

    Lève SimulationError si l'opération est impossible ; l'état d'entrée n'est jamais modifié.
    """
    if tx.currency != state.currency:
        raise SimulationError(
            f"Devise {tx.currency} ≠ devise du portefeuille {state.currency} : "
            "conversion non disponible en V1 (DONNÉES INSUFFISANTES)."
        )
    last = state.last_timestamp
    if last is not None and tx.executed_at < last:
        raise SimulationError("Transaction antérieure à la précédente : l'historique est figé.")

    holdings = dict(state.holdings)
    cash = state.cash
    realized: Decimal | None = None
    op = tx.operation
    symbol = tx.symbol or ""
    current = holdings.get(symbol)

    if op == Op.DEPOSIT:
        cash += _require(tx.amount)
    elif op == Op.WITHDRAWAL:
        amount = _require(tx.amount)
        if amount > cash:
            raise SimulationError(f"Liquidités insuffisantes : {cash} < {amount}")
        cash -= amount
    elif op in (Op.BUY, Op.REINFORCE, Op.IMPORT_POSITION):
        if op == Op.BUY and current is not None:
            raise SimulationError(f"{symbol} déjà détenu : utiliser REINFORCE")
        if op == Op.REINFORCE and current is None:
            raise SimulationError(f"{symbol} non détenu : utiliser BUY")
        if op == Op.IMPORT_POSITION and current is not None:
            raise SimulationError(f"{symbol} déjà présent dans le portefeuille")
        qty, price = _require(tx.quantity), _require(tx.price)
        gross = qty * price
        if op != Op.IMPORT_POSITION:
            debit = _cents(gross + tx.fees)
            if debit > cash:
                raise SimulationError(
                    f"Liquidités insuffisantes pour {symbol} : {cash} < {debit} (frais inclus)"
                )
            cash -= debit
        old_qty = current.quantity if current else ZERO
        old_cost = current.cost_basis if current else ZERO
        new_qty = old_qty + qty
        avg = ((old_cost + gross + tx.fees) / new_qty).quantize(PRICE_PRECISION)
        holdings[symbol] = Holding(quantity=new_qty, average_price=avg)
    elif op in (Op.SELL, Op.REDUCE):
        if current is None:
            raise SimulationError(f"{symbol} non détenu : vente impossible")
        qty, price = _require(tx.quantity), _require(tx.price)
        if op == Op.SELL and qty != current.quantity:
            raise SimulationError(
                f"SELL doit porter sur toute la position ({current.quantity}) : utiliser REDUCE"
            )
        if op == Op.REDUCE and qty >= current.quantity:
            raise SimulationError(
                f"REDUCE doit rester partiel (< {current.quantity}) : utiliser SELL"
            )
        proceeds = _cents(qty * price - tx.fees)
        if proceeds < 0:
            raise SimulationError("Frais supérieurs au produit de la vente")
        cash += proceeds
        realized = _cents(proceeds - qty * current.average_price)
        remaining = current.quantity - qty
        if remaining == 0:
            del holdings[symbol]
        else:
            holdings[symbol] = replace(current, quantity=remaining)
    elif op in (Op.HOLD, Op.WAIT):
        pass  # décision enregistrée, aucun mouvement
    else:  # pragma: no cover — toutes les opérations sont traitées ci-dessus
        raise SimulationError(f"Opération inconnue : {op}")

    return (
        LedgerState(
            currency=state.currency, cash=cash, holdings=holdings, last_timestamp=tx.executed_at
        ),
        realized,
    )


def replay(currency: str, transactions: Iterable[SimulatedTransaction]) -> LedgerState:
    state = LedgerState(currency=currency)
    for tx in transactions:
        state, _ = apply(state, tx)
    return state


def _require(value: Decimal | None) -> Decimal:
    if value is None:  # garanti par la validation du modèle
        raise SimulationError("Valeur manquante")
    return value
