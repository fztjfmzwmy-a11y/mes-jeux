from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

from ai_investor.core.enums import Action, DecisionStatus, JournalEntryType
from ai_investor.core.models import DataReference, JournalRecord
from ai_investor.db.session import init_db, make_engine, make_session_factory
from ai_investor.journal.hashchain import GENESIS_HASH
from ai_investor.journal.repository import JournalRepository
from ai_investor.security.permissions import AgentRole


@pytest.fixture
def engine():
    eng = make_engine("sqlite:///:memory:")
    init_db(eng)
    return eng


@pytest.fixture
def journal(engine):
    return JournalRepository(make_session_factory(engine))


def decision_record(now, source, symbol="CW8"):
    return JournalRecord(
        entry_type=JournalEntryType.DECISION,
        recorded_at=now,
        symbol=symbol,
        action=Action.BUY,
        amount=Decimal("300"),
        price=Decimal("500.12"),
        currency="EUR",
        agents_consulted=(AgentRole.MARKET, AgentRole.RISK_MANAGER),
        data_used=(DataReference(description="cours", source=source, as_of=now),),
        reasoning="Exemple",
        risks=("baisse",),
        final_status=DecisionStatus.BLOCKED,
        risk_rules={"MAX_POSITION_PERCENT": "10"},
    )


def test_append_and_read_back_exactly(journal, now, source):
    record = decision_record(now, source)
    stored = journal.append(record)
    assert stored.seq == 1
    assert journal.get(1).record == record
    assert journal.get(1).record.price == Decimal("500.12")  # Decimal conservé exactement
    assert journal.get(99) is None


def test_chain_links_entries(journal, now, source):
    first = journal.append(decision_record(now, source))
    second = journal.append(decision_record(now, source, "AAPL"))
    assert first.hash != second.hash
    assert journal.verify().ok and journal.verify().entries_checked == 2
    assert journal.head().hash == second.hash
    assert [e.seq for e in journal.list(symbol="AAPL")] == [2]


def test_empty_journal_verifies(journal):
    assert journal.verify().ok and journal.head() is None
    assert len(GENESIS_HASH) == 64


def test_outcome_is_a_separate_entry(journal, now, source):
    decision = journal.append(decision_record(now, source))
    outcome = JournalRecord(
        entry_type=JournalEntryType.OUTCOME,
        recorded_at=now + timedelta(days=30),
        symbol="CW8",
        refers_to=decision.seq,
        details={"price_after": "520", "return_pct": "4"},
    )
    journal.append(outcome)
    assert journal.get(decision.seq).record == decision.record  # la décision n'a pas bougé
    assert [e.record.details["price_after"] for e in journal.outcomes_of(decision.seq)] == ["520"]


def test_outcome_must_target_existing_decision(journal, now, source):
    with pytest.raises(ValueError, match="n'existe pas"):
        journal.append(
            JournalRecord(entry_type=JournalEntryType.OUTCOME, recorded_at=now, refers_to=42)
        )
    event = journal.append(
        JournalRecord(
            entry_type=JournalEntryType.SECURITY_EVENT,
            recorded_at=now,
            reasoning="tentative d'ordre réel",
        )
    )
    with pytest.raises(ValueError):  # un OUTCOME ne peut viser qu'une DECISION
        journal.append(
            JournalRecord(entry_type=JournalEntryType.OUTCOME, recorded_at=now, refers_to=event.seq)
        )


def test_repository_has_no_mutation_methods():
    public = {n for n in dir(JournalRepository) if not n.startswith("_")}
    assert public == {"append", "get", "list", "outcomes_of", "head", "verify"}


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE journal_entries SET payload = '{}' WHERE seq = 1",
        "DELETE FROM journal_entries WHERE seq = 1",
    ],
)
def test_database_refuses_update_and_delete(engine, journal, now, source, sql):
    journal.append(decision_record(now, source))
    with pytest.raises(DatabaseError, match="ajout seul"), engine.begin() as conn:
        conn.execute(text(sql))
    assert journal.verify().ok


def _tamper(engine, sql):
    with engine.begin() as conn:
        conn.execute(text("DROP TRIGGER journal_entries_no_update"))
        conn.execute(text("DROP TRIGGER journal_entries_no_delete"))
        conn.execute(text(sql))


def test_tampering_outside_the_app_is_detected(engine, journal, now, source):
    for _ in range(3):
        journal.append(decision_record(now, source))
    _tamper(
        engine,
        "UPDATE journal_entries SET payload = "
        "replace(payload, 'BLOCKED', 'APPROVED') WHERE seq = 2",
    )
    report = journal.verify()
    assert not report.ok and report.first_invalid_seq == 2 and report.reason == "contenu modifié"


def test_deleted_middle_entry_is_detected(engine, journal, now, source):
    for _ in range(3):
        journal.append(decision_record(now, source))
    _tamper(engine, "DELETE FROM journal_entries WHERE seq = 2")
    report = journal.verify()
    assert not report.ok and report.first_invalid_seq == 3


def test_truncation_detected_with_saved_head(engine, journal, now, source):
    for _ in range(3):
        journal.append(decision_record(now, source))
    saved_head = journal.head().hash
    _tamper(engine, "DELETE FROM journal_entries WHERE seq = 3")
    assert journal.verify().ok  # limite connue : sans référence externe, invisible
    assert not journal.verify(expected_head_hash=saved_head).ok


def test_simulated_transactions_table_is_append_only(engine):
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO portfolios (name, base_currency, created_at) "
                "VALUES ('v', 'EUR', '2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO simulated_transactions "
                "(portfolio_id, executed_at, operation, payload) "
                "VALUES (1, '2026-01-01', 'BUY', '{}')"
            )
        )
    for sql in (
        "UPDATE simulated_transactions SET operation = 'SELL'",
        "DELETE FROM simulated_transactions",
    ):
        with pytest.raises(DatabaseError), engine.begin() as conn:
            conn.execute(text(sql))


def test_foreign_keys_enforced(engine):
    with pytest.raises(DatabaseError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO simulated_transactions "
                "(portfolio_id, executed_at, operation, payload) "
                "VALUES (999, '2026-01-01', 'BUY', '{}')"
            )
        )


def test_file_database_persists(tmp_path, now, source):
    url = f"sqlite:///{tmp_path / 'j.db'}"
    eng = make_engine(url)
    init_db(eng)
    JournalRepository(make_session_factory(eng)).append(decision_record(now, source))
    eng.dispose()
    eng2 = make_engine(url)
    init_db(eng2)  # idempotent
    repo = JournalRepository(make_session_factory(eng2))
    assert repo.verify().ok and repo.verify().entries_checked == 1
