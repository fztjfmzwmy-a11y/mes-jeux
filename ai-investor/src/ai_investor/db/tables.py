"""Schéma SQL (SQLAlchemy 2).

Tables immuables (append-only, protégées par des triggers SQLite) :
- journal_entries : journal des décisions, chaîné par hash ;
- simulated_transactions : historique des opérations du portefeuille virtuel.

Les colonnes monétaires sont stockées en texte (Decimal exact), jamais en float.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PortfolioRow(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    base_currency: Mapped[str] = mapped_column(String(3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fee_fixed: Mapped[str] = mapped_column(String(40), server_default="0")
    fee_percent: Mapped[str] = mapped_column(String(40), server_default="0")


class AssetRow(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True)
    isin: Mapped[str | None] = mapped_column(String(12), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    asset_type: Mapped[str] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(3))
    sector: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100))
    tracked_index: Mapped[str | None] = mapped_column(String(200))


class PositionRow(Base):
    """État courant d'une position du portefeuille virtuel (dérivé des transactions)."""

    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("portfolio_id", "asset_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"))
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    quantity: Mapped[str] = mapped_column(String(40))
    average_price: Mapped[str] = mapped_column(String(40))


class CashRow(Base):
    __tablename__ = "cash_balances"
    __table_args__ = (UniqueConstraint("portfolio_id", "currency"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"))
    currency: Mapped[str] = mapped_column(String(3))
    amount: Mapped[str] = mapped_column(String(40))


class SimulatedTransactionRow(Base):
    __tablename__ = "simulated_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"))
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    operation: Mapped[str] = mapped_column(String(20))
    payload: Mapped[str] = mapped_column(Text)  # JSON canonique du modèle


class PriceBarRow(Base):
    __tablename__ = "price_bars"
    __table_args__ = (UniqueConstraint("symbol", "day", "source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    day: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(100))
    payload: Mapped[str] = mapped_column(Text)


class JournalEntryRow(Base):
    __tablename__ = "journal_entries"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    entry_type: Mapped[str] = mapped_column(String(20), index=True)
    symbol: Mapped[str | None] = mapped_column(String(32), index=True)
    refers_to: Mapped[int | None] = mapped_column(ForeignKey("journal_entries.seq"))
    payload: Mapped[str] = mapped_column(Text)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


APPEND_ONLY_TABLES = ("journal_entries", "simulated_transactions")
