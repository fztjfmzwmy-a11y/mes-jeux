"""Moteur SQLite, clés étrangères actives, triggers d'immuabilité."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from ai_investor.db.tables import APPEND_ONLY_TABLES, Base


def _enable_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def make_engine(url: str = "sqlite:///:memory:") -> Engine:
    kwargs: dict[str, Any] = {}
    if url.endswith(":memory:"):
        from sqlalchemy.pool import StaticPool

        kwargs = {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
    engine = create_engine(url, **kwargs)
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _enable_foreign_keys)
    return engine


def init_db(engine: Engine) -> None:
    """Crée les tables et les triggers qui interdisent UPDATE/DELETE sur les tables immuables."""
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for table in APPEND_ONLY_TABLES:
            for op in ("UPDATE", "DELETE"):
                conn.execute(
                    text(
                        f"CREATE TRIGGER IF NOT EXISTS {table}_no_{op.lower()} "
                        f"BEFORE {op} ON {table} BEGIN "
                        f"SELECT RAISE(ABORT, '{table} est en ajout seul : {op} interdit'); END"
                    )
                )


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
