from datetime import timedelta
from decimal import Decimal as D

import pytest
from sqlalchemy import text

from ai_investor.core.enums import AssetType, SimulatedOperation
from ai_investor.core.errors import SimulationError
from ai_investor.core.models import Asset, Position
from ai_investor.db.session import init_db, make_engine, make_session_factory
from ai_investor.portfolio.fees import FeeModel
from ai_investor.portfolio.provider import VirtualPortfolioProvider
from ai_investor.portfolio.simulator import VirtualPortfolioService, quantity_for_amount

CW8 = Asset(
    symbol="CW8", name="MSCI World", asset_type=AssetType.ETF, currency="EUR", isin="LU1681043599"
)
AIR = Asset(
    symbol="AIR", name="Airbus", asset_type=AssetType.STOCK, currency="EUR", sector="Industrie"
)
AAPL = Asset(symbol="AAPL", name="Apple", asset_type=AssetType.STOCK, currency="USD")


@pytest.fixture
def engine():
    eng = make_engine()
    init_db(eng)
    return eng


@pytest.fixture
def service(engine, now):
    svc = VirtualPortfolioService(make_session_factory(engine))
    svc.create_portfolio("virtuel", "EUR", D(10000), FeeModel(fixed=D(1)), now)
    return svc


def t(now, minutes):
    return now + timedelta(minutes=minutes)


def test_initial_capital_recorded_as_deposit(service, now):
    snap = service.snapshot("virtuel", now)
    assert snap.cash[0].amount == D(10000) and snap.positions == ()
    [deposit] = service.transactions("virtuel")
    assert deposit.operation == SimulatedOperation.DEPOSIT and deposit.simulated


def test_duplicate_or_unknown_portfolio(service, now):
    with pytest.raises(SimulationError, match="existe déjà"):
        service.create_portfolio("virtuel", "EUR", D(0), FeeModel(), now)
    with pytest.raises(SimulationError, match="inconnu"):
        service.snapshot("autre", now)


def test_full_cycle_buy_reinforce_reduce_sell(service, now):
    r = service.simulate_buy("virtuel", CW8, D(5), D(500), t(now, 1))
    assert r.transaction.operation == SimulatedOperation.BUY and r.transaction.fees == D(1)
    r = service.simulate_buy("virtuel", CW8, D(5), D(520), t(now, 2))
    assert r.transaction.operation == SimulatedOperation.REINFORCE
    pos = service.snapshot("virtuel", now).positions[0]
    assert pos.quantity == D(10) and pos.average_price == D("510.2")
    r = service.simulate_sell("virtuel", CW8, D(2), D(530), t(now, 3))
    assert r.transaction.operation == SimulatedOperation.REDUCE
    assert r.transaction.realized_pnl == D("38.60")
    r = service.simulate_sell("virtuel", CW8, D(8), D(530), t(now, 4))
    assert r.transaction.operation == SimulatedOperation.SELL
    assert service.snapshot("virtuel", now).positions == ()
    assert service.check_consistency("virtuel").ok
    ops = [x.operation for x in service.transactions("virtuel")]
    assert ops == ["DEPOSIT", "BUY", "REINFORCE", "REDUCE", "SELL"]


def test_hold_wait_are_recorded(service, now):
    service.record_hold("virtuel", AIR, t(now, 1), decision_ref=3, note="attente résultats")
    service.record_wait("virtuel", CW8, t(now, 2))
    txs = service.transactions("virtuel")
    assert [x.operation for x in txs[1:]] == ["HOLD", "WAIT"] and txs[1].decision_ref == 3
    assert service.snapshot("virtuel", now).cash[0].amount == D(10000)


def test_failed_operation_leaves_no_trace(service, now):
    with pytest.raises(SimulationError, match="insuffisantes"):
        service.simulate_buy("virtuel", CW8, D(100), D(500), t(now, 1))
    assert len(service.transactions("virtuel")) == 1
    assert service.snapshot("virtuel", now).positions == ()


def test_foreign_currency_asset_refused(service, now):
    with pytest.raises(SimulationError, match="conversion"):
        service.simulate_buy("virtuel", AAPL, D(1), D(200), t(now, 1))


def test_isin_conflict_detected(service, now):
    service.simulate_buy("virtuel", CW8, D(1), D(500), t(now, 1))
    fake = CW8.model_copy(update={"isin": "FR0011869353"})
    with pytest.raises(SimulationError, match="ISIN"):
        service.simulate_buy("virtuel", fake, D(1), D(500), t(now, 2))


def test_backdating_refused(service, now):
    service.simulate_buy("virtuel", CW8, D(1), D(500), t(now, 10))
    with pytest.raises(SimulationError, match="figé"):
        service.simulate_buy("virtuel", AIR, D(1), D(100), t(now, 5))


def test_import_positions_and_provider(service, now):
    service.import_positions(
        "virtuel", [Position(asset=AIR, quantity=D(8), average_price=D(128))], t(now, 1)
    )
    provider = VirtualPortfolioProvider(service, "virtuel", clock=lambda: now)
    assert [p.asset.symbol for p in provider.get_positions()] == ["AIR"]
    assert provider.get_cash_balances()[0].amount == D(10000)
    assert provider.info.reliability == "SIMULATED"


def test_consistency_detects_tampered_state(engine, service, now):
    service.simulate_buy("virtuel", CW8, D(2), D(500), t(now, 1))
    with engine.begin() as conn:
        conn.execute(text("UPDATE cash_balances SET amount = '999999'"))
    report = service.check_consistency("virtuel")
    assert not report.ok and "liquidités" in report.differences[0]


def test_quantity_for_amount_is_conservative():
    q = quantity_for_amount(D(300), D("412.37"), FeeModel(fixed=D(1)))
    assert q * D("412.37") + D(1) <= D(300)
    with pytest.raises(SimulationError):
        quantity_for_amount(D("0.5"), D(10), FeeModel(fixed=D(1)))


def test_timezone_preserved_across_reload(service, now):
    from datetime import timezone

    paris = now.astimezone(timezone(timedelta(hours=2)))
    service.simulate_buy("virtuel", CW8, D(1), D(500), paris + timedelta(minutes=1))
    # 1 minute plus tard en UTC : doit être accepté (même instant de référence).
    service.simulate_buy("virtuel", AIR, D(1), D(100), now + timedelta(minutes=2))
    assert service.check_consistency("virtuel").ok
