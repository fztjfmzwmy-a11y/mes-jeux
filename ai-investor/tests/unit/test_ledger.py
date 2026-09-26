from datetime import timedelta
from decimal import Decimal as D

import pytest

from ai_investor.core.enums import SimulatedOperation as Op
from ai_investor.core.errors import SimulationError
from ai_investor.core.models import SimulatedTransaction
from ai_investor.portfolio.fees import FeeModel
from ai_investor.portfolio.ledger import Holding, LedgerState, apply, replay


def tx(now, op, offset=0, **kw):
    return SimulatedTransaction(
        portfolio="v",
        executed_at=now + timedelta(minutes=offset),
        operation=op,
        currency="EUR",
        **kw,
    )


def funded(now, amount="1000"):
    state, _ = apply(LedgerState("EUR"), tx(now, Op.DEPOSIT, amount=D(amount)))
    return state


def test_buy_includes_fees_in_average_price(now):
    state, pnl = apply(
        funded(now), tx(now, Op.BUY, 1, symbol="CW8", quantity=D(2), price=D(100), fees=D(1))
    )
    assert pnl is None
    assert state.cash == D("799.00")
    assert state.holdings["CW8"] == Holding(D(2), D("100.50000000"))


def test_reinforce_weighted_average(now):
    s, _ = apply(funded(now), tx(now, Op.BUY, 1, symbol="X", quantity=D(1), price=D(100)))
    s, _ = apply(s, tx(now, Op.REINFORCE, 2, symbol="X", quantity=D(3), price=D(200)))
    assert s.holdings["X"] == Holding(D(4), D(175))
    assert s.cash == D(300)


def test_reduce_then_sell_realized_pnl(now):
    s, _ = apply(funded(now), tx(now, Op.BUY, 1, symbol="X", quantity=D(4), price=D(100)))
    s, pnl = apply(s, tx(now, Op.REDUCE, 2, symbol="X", quantity=D(1), price=D(120), fees=D(1)))
    assert pnl == D("19.00") and s.holdings["X"].quantity == D(3)
    assert s.holdings["X"].average_price == D(100)  # PRU inchangé par une réduction
    s, pnl = apply(s, tx(now, Op.SELL, 3, symbol="X", quantity=D(3), price=D(90)))
    assert pnl == D("-30.00") and "X" not in s.holdings
    assert s.cash == D(1000) - D(400) + D(119) + D(270)


@pytest.mark.parametrize(
    "op,kw,match",
    [
        (Op.BUY, dict(symbol="X", quantity=D(20), price=D(100)), "insuffisantes"),
        (Op.BUY, dict(symbol="X", quantity=D(10), price=D(100), fees=D(1)), "frais inclus"),
        (Op.REINFORCE, dict(symbol="X", quantity=D(1), price=D(1)), "non détenu"),
        (Op.SELL, dict(symbol="X", quantity=D(1), price=D(1)), "non détenu"),
        (Op.WITHDRAWAL, dict(amount=D(5000)), "insuffisantes"),
    ],
)
def test_impossible_operations(now, op, kw, match):
    with pytest.raises(SimulationError, match=match):
        apply(funded(now), tx(now, op, 1, **kw))


def test_sell_must_be_total_and_reduce_partial(now):
    s, _ = apply(funded(now), tx(now, Op.BUY, 1, symbol="X", quantity=D(2), price=D(10)))
    with pytest.raises(SimulationError, match="REDUCE"):
        apply(s, tx(now, Op.SELL, 2, symbol="X", quantity=D(1), price=D(10)))
    with pytest.raises(SimulationError, match="SELL"):
        apply(s, tx(now, Op.REDUCE, 2, symbol="X", quantity=D(2), price=D(10)))
    with pytest.raises(SimulationError, match="REINFORCE"):
        apply(s, tx(now, Op.BUY, 2, symbol="X", quantity=D(1), price=D(10)))


def test_hold_and_wait_change_nothing(now):
    s = funded(now)
    for op in (Op.HOLD, Op.WAIT):
        s2, pnl = apply(s, tx(now, op, 1, symbol="X"))
        assert (s2.cash, s2.holdings, pnl) == (s.cash, s.holdings, None)


def test_import_position_does_not_touch_cash(now):
    s, _ = apply(
        funded(now), tx(now, Op.IMPORT_POSITION, 1, symbol="X", quantity=D(5), price=D(50))
    )
    assert s.cash == D(1000) and s.holdings["X"] == Holding(D(5), D(50))


def test_other_currency_refused(now):
    with pytest.raises(SimulationError, match="conversion"):
        apply(
            LedgerState("EUR"),
            SimulatedTransaction(
                portfolio="v", executed_at=now, operation=Op.DEPOSIT, currency="USD", amount=D(1)
            ),
        )


def test_backdated_transaction_refused(now):
    s = funded(now)
    with pytest.raises(SimulationError, match="figé"):
        apply(s, tx(now, Op.DEPOSIT, -60, amount=D(1)))


def test_input_state_never_mutated(now):
    s = funded(now)
    apply(s, tx(now, Op.BUY, 1, symbol="X", quantity=D(1), price=D(10)))
    assert s.holdings == {} and s.cash == D(1000)


def test_replay_reproduces_state(now):
    txs = [
        tx(now, Op.DEPOSIT, amount=D(1000)),
        tx(now, Op.BUY, 1, symbol="X", quantity=D(3), price=D(100), fees=D(1)),
        tx(now, Op.REDUCE, 2, symbol="X", quantity=D(1), price=D(110), fees=D(1)),
    ]
    state = replay("EUR", txs)
    assert state.cash == D("808.00") and state.holdings["X"].quantity == D(2)


def test_fee_model():
    fees = FeeModel(fixed=D(1), percent=D("0.25"))
    assert fees.fee_for(D(1000)) == D("3.50")
    assert FeeModel().fee_for(D(1000)) == D(0)
    with pytest.raises(ValueError):
        FeeModel(fixed=D(-1))
