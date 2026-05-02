"""Modeles SQLAlchemy."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class BetDirection(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


class BetStatus(str, Enum):
    PENDING = "PENDING"
    WON = "WON"
    LOST = "LOST"
    SKIPPED = "SKIPPED"


class Bet(Base):
    __tablename__ = "bets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    mode: Mapped[str] = mapped_column(String(8), default="demo")  # demo|prod
    market: Mapped[str] = mapped_column(String(64), default="BTC-5min")
    direction: Mapped[str] = mapped_column(String(4))  # UP|DOWN
    amount: Mapped[float] = mapped_column(Float, default=0.0)

    entry_price: Mapped[float] = mapped_column(Float, default=0.0)
    polymarket_price: Mapped[float] = mapped_column(Float, default=0.0)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    status: Mapped[str] = mapped_column(String(16), default=BetStatus.PENDING.value, index=True)
    pnl: Mapped[float] = mapped_column(Float, default=0.0)

    signal_candle: Mapped[str] = mapped_column(String(8), default="")
    signal_binance_trend: Mapped[str] = mapped_column(String(8), default="")
    notes: Mapped[str] = mapped_column(String(255), default="")
    # Strategie qui a place le pari : "candle" (double confirmation bougie + trend Binance)
    # ou "arbitrage" (lag carnet Polymarket vs Binance). Permet de comparer les win rates
    # quand SIGNAL_MODE=both.
    strategy: Mapped[str] = mapped_column(String(16), default="candle", index=True)
