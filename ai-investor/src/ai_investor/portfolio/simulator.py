"""Portefeuille VIRTUEL persistant.

Toutes les opérations sont fictives : aucun ordre n'est transmis à qui que ce soit.
Chaque opération est validée par `ledger.apply`, puis enregistrée dans la table
`simulated_transactions` (ajout seul) ; l'état courant (positions, liquidités) est
mis à jour dans la même transaction SQL.

Ce module applique uniquement les contraintes « physiques » (liquidités, quantités).
Les règles de risque (limites, actifs interdits…) relèvent du Risk Manager (étape 9).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ai_investor.core.enums import SimulatedOperation
from ai_investor.core.errors import SimulationError
from ai_investor.core.models import (
    Asset,
    CashBalance,
    PortfolioSnapshot,
    Position,
    SimulatedTransaction,
)
from ai_investor.db.tables import AssetRow, CashRow, PortfolioRow, PositionRow
from ai_investor.db.tables import SimulatedTransactionRow as TxRow
from ai_investor.journal.hashchain import canonical_json
from ai_investor.portfolio import ledger
from ai_investor.portfolio.fees import FeeModel

Op = SimulatedOperation
QUANTITY_PRECISION = Decimal("0.000001")  # fractions d'actions


@dataclass(frozen=True)
class SimulationResult:
    transaction: SimulatedTransaction
    cash_after: Decimal


@dataclass(frozen=True)
class ConsistencyReport:
    ok: bool
    differences: tuple[str, ...] = ()


def quantity_for_amount(amount: Decimal, price: Decimal, fees: FeeModel) -> Decimal:
    """Quantité achetable pour un montant total (frais inclus), arrondie à l'inférieur."""
    if amount <= 0 or price <= 0:
        raise SimulationError("Montant et prix doivent être positifs")
    # Approximation conservatrice : frais estimés sur le montant total.
    net = amount - fees.fee_for(amount)
    if net <= 0:
        raise SimulationError("Montant inférieur aux frais")
    return (net / price).quantize(QUANTITY_PRECISION, rounding=ROUND_DOWN)


class VirtualPortfolioService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    # --- Création / lecture ------------------------------------------------------------

    def create_portfolio(
        self,
        name: str,
        base_currency: str,
        initial_capital: Decimal,
        fees: FeeModel,
        at: datetime,
    ) -> None:
        with self._sessions.begin() as session:
            if session.scalars(select(PortfolioRow).where(PortfolioRow.name == name)).first():
                raise SimulationError(f"Le portefeuille {name!r} existe déjà")
            session.add(
                PortfolioRow(
                    name=name,
                    base_currency=base_currency,
                    created_at=at,
                    fee_fixed=str(fees.fixed),
                    fee_percent=str(fees.percent),
                )
            )
        if initial_capital > 0:
            self.deposit(name, initial_capital, at, note="Capital initial")

    def fees(self, name: str) -> FeeModel:
        with self._sessions() as session:
            row = self._portfolio(session, name)
            return FeeModel(fixed=Decimal(row.fee_fixed), percent=Decimal(row.fee_percent))

    def snapshot(self, name: str, as_of: datetime) -> PortfolioSnapshot:
        with self._sessions() as session:
            row = self._portfolio(session, name)
            positions = tuple(
                Position(
                    asset=_asset_from_row(asset),
                    quantity=Decimal(pos.quantity),
                    average_price=Decimal(pos.average_price),
                )
                for pos, asset in session.execute(
                    select(PositionRow, AssetRow)
                    .join(AssetRow, PositionRow.asset_id == AssetRow.id)
                    .where(PositionRow.portfolio_id == row.id)
                    .order_by(AssetRow.symbol)
                )
            )
            cash = tuple(
                CashBalance(amount=Decimal(c.amount), currency=c.currency)
                for c in session.scalars(select(CashRow).where(CashRow.portfolio_id == row.id))
            )
            return PortfolioSnapshot(
                name=name,
                base_currency=row.base_currency,
                as_of=as_of,
                positions=positions,
                cash=cash,
            )

    def transactions(self, name: str) -> Sequence[SimulatedTransaction]:
        with self._sessions() as session:
            row = self._portfolio(session, name)
            return [
                SimulatedTransaction.model_validate_json(tx.payload)
                for tx in session.scalars(
                    select(TxRow).where(TxRow.portfolio_id == row.id).order_by(TxRow.id)
                )
            ]

    def check_consistency(self, name: str) -> ConsistencyReport:
        """Recalcule l'état à partir de l'historique et le compare à l'état stocké."""
        with self._sessions() as session:
            row = self._portfolio(session, name)
            currency = row.base_currency
        try:
            expected = ledger.replay(currency, self.transactions(name))
        except SimulationError as exc:
            return ConsistencyReport(False, (f"Historique invalide : {exc}",))
        with self._sessions() as session:
            stored = self._load_state(session, self._portfolio(session, name))
        diffs: list[str] = []
        if expected.cash != stored.cash:
            diffs.append(f"liquidités : attendu {expected.cash}, stocké {stored.cash}")
        for symbol in sorted(set(expected.holdings) | set(stored.holdings)):
            if expected.holdings.get(symbol) != stored.holdings.get(symbol):
                diffs.append(
                    f"{symbol} : attendu {expected.holdings.get(symbol)}, "
                    f"stocké {stored.holdings.get(symbol)}"
                )
        return ConsistencyReport(not diffs, tuple(diffs))

    # --- Opérations simulées -----------------------------------------------------------

    def deposit(self, name: str, amount: Decimal, at: datetime, note: str = "") -> SimulationResult:
        return self._record(name, None, Op.DEPOSIT, at, amount=amount, note=note)

    def virtual_cash_out(
        self, name: str, amount: Decimal, at: datetime, note: str = ""
    ) -> SimulationResult:
        """Retire du capital VIRTUEL du portefeuille simulé (aucun argent réel)."""
        return self._record(name, None, Op.WITHDRAWAL, at, amount=amount, note=note)

    def simulate_buy(
        self,
        name: str,
        asset: Asset,
        quantity: Decimal,
        price: Decimal,
        at: datetime,
        decision_ref: int | None = None,
        note: str = "",
    ) -> SimulationResult:
        """Achat (nouvelle position) ou renforcement (position déjà détenue)."""
        op = Op.REINFORCE if self._holds(name, asset.symbol) else Op.BUY
        return self._trade(name, asset, op, quantity, price, at, decision_ref, note)

    def simulate_sell(
        self,
        name: str,
        asset: Asset,
        quantity: Decimal,
        price: Decimal,
        at: datetime,
        decision_ref: int | None = None,
        note: str = "",
    ) -> SimulationResult:
        """Vente totale (SELL) si la quantité égale la position, sinon réduction (REDUCE)."""
        snapshot = self.snapshot(name, at)
        held = next(
            (p.quantity for p in snapshot.positions if p.asset.symbol == asset.symbol), None
        )
        op = Op.SELL if held is not None and quantity == held else Op.REDUCE
        return self._trade(name, asset, op, quantity, price, at, decision_ref, note)

    def record_hold(
        self, name: str, asset: Asset, at: datetime, decision_ref: int | None = None, note: str = ""
    ) -> SimulationResult:
        return self._record(name, asset, Op.HOLD, at, decision_ref=decision_ref, note=note)

    def record_wait(
        self, name: str, asset: Asset, at: datetime, decision_ref: int | None = None, note: str = ""
    ) -> SimulationResult:
        return self._record(name, asset, Op.WAIT, at, decision_ref=decision_ref, note=note)

    def import_positions(
        self, name: str, positions: Sequence[Position], at: datetime, note: str = "Import"
    ) -> list[SimulationResult]:
        """Reprend des positions existantes (sans débit de liquidités), au PRU fourni."""
        return [
            self._record(
                name,
                p.asset,
                Op.IMPORT_POSITION,
                at,
                quantity=p.quantity,
                price=p.average_price,
                note=note,
            )
            for p in positions
        ]

    # --- Interne -----------------------------------------------------------------------

    def _trade(
        self,
        name: str,
        asset: Asset,
        op: SimulatedOperation,
        quantity: Decimal,
        price: Decimal,
        at: datetime,
        decision_ref: int | None,
        note: str,
    ) -> SimulationResult:
        fees = self.fees(name).fee_for(quantity * price)
        return self._record(
            name,
            asset,
            op,
            at,
            quantity=quantity,
            price=price,
            fees=fees,
            decision_ref=decision_ref,
            note=note,
        )

    def _holds(self, name: str, symbol: str) -> bool:
        with self._sessions() as session:
            row = self._portfolio(session, name)
            return symbol.upper() in self._load_state(session, row).holdings

    def _record(
        self,
        name: str,
        asset: Asset | None,
        op: SimulatedOperation,
        at: datetime,
        *,
        quantity: Decimal | None = None,
        price: Decimal | None = None,
        amount: Decimal | None = None,
        fees: Decimal = Decimal("0"),
        decision_ref: int | None = None,
        note: str = "",
    ) -> SimulationResult:
        with self._sessions.begin() as session:
            portfolio = self._portfolio(session, name)
            if asset is not None and asset.currency != portfolio.base_currency:
                raise SimulationError(
                    f"{asset.symbol} est coté en {asset.currency}, portefeuille en "
                    f"{portfolio.base_currency} : conversion non disponible en V1."
                )
            state = self._load_state(session, portfolio)
            draft = SimulatedTransaction(
                portfolio=name,
                executed_at=at,
                operation=op,
                currency=portfolio.base_currency,
                symbol=asset.symbol if asset else None,
                quantity=quantity,
                price=price,
                amount=amount,
                fees=fees,
                decision_ref=decision_ref,
                note=note,
            )
            new_state, realized = ledger.apply(state, draft)
            tx = (
                SimulatedTransaction.model_validate(
                    {**draft.model_dump(), "realized_pnl": realized}
                )
                if realized is not None
                else draft
            )
            session.add(
                TxRow(
                    portfolio_id=portfolio.id,
                    executed_at=at,
                    operation=op,
                    payload=canonical_json(tx),
                )
            )
            asset_id = self._ensure_asset(session, asset) if asset is not None else None
            self._store_state(session, portfolio, new_state, asset, asset_id)
            return SimulationResult(transaction=tx, cash_after=new_state.cash)

    @staticmethod
    def _portfolio(session: Session, name: str) -> PortfolioRow:
        row = session.scalars(select(PortfolioRow).where(PortfolioRow.name == name)).first()
        if row is None:
            raise SimulationError(f"Portefeuille inconnu : {name!r}")
        return row

    @staticmethod
    def _ensure_asset(session: Session, asset: Asset) -> int:
        row = session.scalars(select(AssetRow).where(AssetRow.symbol == asset.symbol)).first()
        if row is not None:
            if asset.isin and row.isin and asset.isin != row.isin:
                raise SimulationError(
                    f"{asset.symbol} : ISIN {asset.isin} différent de l'ISIN connu {row.isin}"
                )
            return row.id
        row = AssetRow(
            symbol=asset.symbol,
            isin=asset.isin,
            name=asset.name,
            asset_type=asset.asset_type,
            currency=asset.currency,
            sector=asset.sector,
            region=asset.region,
            country=asset.country,
            tracked_index=asset.tracked_index,
        )
        session.add(row)
        session.flush()
        return row.id

    @staticmethod
    def _load_state(session: Session, portfolio: PortfolioRow) -> ledger.LedgerState:
        cash_row = session.scalars(
            select(CashRow).where(
                CashRow.portfolio_id == portfolio.id, CashRow.currency == portfolio.base_currency
            )
        ).first()
        holdings = {
            asset.symbol: ledger.Holding(Decimal(pos.quantity), Decimal(pos.average_price))
            for pos, asset in session.execute(
                select(PositionRow, AssetRow)
                .join(AssetRow, PositionRow.asset_id == AssetRow.id)
                .where(PositionRow.portfolio_id == portfolio.id)
            )
        }
        # La date de référence est lue dans le JSON (fuseau horaire conservé), pas dans la
        # colonne SQL : SQLite ne stocke pas le fuseau.
        last_payload = session.scalars(
            select(TxRow.payload)
            .where(TxRow.portfolio_id == portfolio.id)
            .order_by(TxRow.id.desc())
            .limit(1)
        ).first()
        last = (
            SimulatedTransaction.model_validate_json(last_payload).executed_at
            if last_payload
            else None
        )
        return ledger.LedgerState(
            currency=portfolio.base_currency,
            cash=Decimal(cash_row.amount) if cash_row else Decimal("0"),
            holdings=holdings,
            last_timestamp=last,
        )

    @staticmethod
    def _store_state(
        session: Session,
        portfolio: PortfolioRow,
        state: ledger.LedgerState,
        asset: Asset | None,
        asset_id: int | None,
    ) -> None:
        cash_row = session.scalars(
            select(CashRow).where(
                CashRow.portfolio_id == portfolio.id, CashRow.currency == state.currency
            )
        ).first()
        if cash_row is None:
            session.add(
                CashRow(portfolio_id=portfolio.id, currency=state.currency, amount=str(state.cash))
            )
        else:
            cash_row.amount = str(state.cash)
        if asset is None or asset_id is None:
            return
        pos_row = session.scalars(
            select(PositionRow).where(
                PositionRow.portfolio_id == portfolio.id, PositionRow.asset_id == asset_id
            )
        ).first()
        holding = state.holdings.get(asset.symbol)
        if holding is None:
            if pos_row is not None:
                session.delete(pos_row)
        elif pos_row is None:
            session.add(
                PositionRow(
                    portfolio_id=portfolio.id,
                    asset_id=asset_id,
                    quantity=str(holding.quantity),
                    average_price=str(holding.average_price),
                )
            )
        else:
            pos_row.quantity = str(holding.quantity)
            pos_row.average_price = str(holding.average_price)


def _asset_from_row(row: AssetRow) -> Asset:
    return Asset.model_validate(
        {
            "symbol": row.symbol,
            "isin": row.isin,
            "name": row.name,
            "asset_type": row.asset_type,
            "currency": row.currency,
            "sector": row.sector,
            "region": row.region,
            "country": row.country,
            "tracked_index": row.tracked_index,
        }
    )
