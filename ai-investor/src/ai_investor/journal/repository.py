"""Journal des décisions : ajout et lecture uniquement.

Il n'existe volontairement aucune méthode de modification ou de suppression.
La base refuse par ailleurs UPDATE/DELETE (triggers), et le chaînage par hash
permet de détecter une altération faite hors de l'application.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ai_investor.core.enums import JournalEntryType
from ai_investor.core.models.journal import JournalRecord
from ai_investor.db.tables import JournalEntryRow
from ai_investor.journal.hashchain import GENESIS_HASH, canonical_json, entry_hash


@dataclass(frozen=True)
class StoredEntry:
    seq: int
    hash: str
    record: JournalRecord


@dataclass(frozen=True)
class ChainReport:
    ok: bool
    entries_checked: int
    first_invalid_seq: int | None = None
    reason: str | None = None


class JournalRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    def append(self, record: JournalRecord) -> StoredEntry:
        with self._sessions.begin() as session:
            if record.entry_type == JournalEntryType.OUTCOME:
                target = session.get(JournalEntryRow, record.refers_to)
                if target is None or target.entry_type != JournalEntryType.DECISION:
                    raise ValueError(f"OUTCOME : la décision n°{record.refers_to} n'existe pas")
            last = session.scalars(
                select(JournalEntryRow).order_by(JournalEntryRow.seq.desc()).limit(1)
            ).first()
            seq = (last.seq if last else 0) + 1
            prev_hash = last.hash if last else GENESIS_HASH
            payload = canonical_json(record)
            digest = entry_hash(seq, prev_hash, payload)
            session.add(
                JournalEntryRow(
                    seq=seq,
                    recorded_at=record.recorded_at,
                    entry_type=record.entry_type,
                    symbol=record.symbol,
                    refers_to=record.refers_to,
                    payload=payload,
                    prev_hash=prev_hash,
                    hash=digest,
                )
            )
        return StoredEntry(seq=seq, hash=digest, record=record)

    def get(self, seq: int) -> StoredEntry | None:
        with self._sessions() as session:
            row = session.get(JournalEntryRow, seq)
            return None if row is None else _to_entry(row)

    def list(
        self, entry_type: JournalEntryType | None = None, symbol: str | None = None
    ) -> Sequence[StoredEntry]:
        query = select(JournalEntryRow).order_by(JournalEntryRow.seq)
        if entry_type is not None:
            query = query.where(JournalEntryRow.entry_type == entry_type)
        if symbol is not None:
            query = query.where(JournalEntryRow.symbol == symbol)
        with self._sessions() as session:
            return [_to_entry(row) for row in session.scalars(query)]

    def outcomes_of(self, decision_seq: int) -> Sequence[StoredEntry]:
        query = (
            select(JournalEntryRow)
            .where(JournalEntryRow.refers_to == decision_seq)
            .order_by(JournalEntryRow.seq)
        )
        with self._sessions() as session:
            return [_to_entry(row) for row in session.scalars(query)]

    def head(self) -> StoredEntry | None:
        """Dernière entrée. Conserver son hash hors de la base (export, note) permet aussi de
        détecter la suppression des dernières entrées, que le chaînage seul ne révèle pas."""
        with self._sessions() as session:
            row = session.scalars(
                select(JournalEntryRow).order_by(JournalEntryRow.seq.desc()).limit(1)
            ).first()
            return None if row is None else _to_entry(row)

    def verify(self, expected_head_hash: str | None = None) -> ChainReport:
        """Recalcule toute la chaîne. Signale la première entrée altérée, supprimée ou déplacée."""
        prev_hash = GENESIS_HASH
        expected_seq = 1
        count = 0
        seen: set[str] = set()
        with self._sessions() as session:
            for row in session.scalars(select(JournalEntryRow).order_by(JournalEntryRow.seq)):
                count += 1
                if row.seq != expected_seq:
                    return ChainReport(False, count, row.seq, "entrée manquante avant celle-ci")
                if row.prev_hash != prev_hash:
                    return ChainReport(False, count, row.seq, "chaînage rompu")
                if entry_hash(row.seq, row.prev_hash, row.payload) != row.hash:
                    return ChainReport(False, count, row.seq, "contenu modifié")
                prev_hash = row.hash
                expected_seq += 1
                seen.add(row.hash)
        if expected_head_hash is not None and expected_head_hash not in seen:
            return ChainReport(False, count, None, "entrée de référence introuvable (troncature)")
        return ChainReport(True, count)


def _to_entry(row: JournalEntryRow) -> StoredEntry:
    return StoredEntry(
        seq=row.seq, hash=row.hash, record=JournalRecord.model_validate_json(row.payload)
    )
