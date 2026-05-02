"""Etat partage du bot expose par l'API et le dashboard."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class BotState:
    """Snapshot temps reel du bot."""

    running: bool = False
    mode: str = "demo"
    bet_amount: float = 5.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    target_market: str = "BTC-5min"

    btc_price: float = 0.0
    btc_trend: str = ""  # UP / DOWN / FLAT
    last_candle_color: str = ""  # GREEN / RED / NONE
    current_signal: str = "INCERTAIN"  # UP / DOWN / INCERTAIN
    next_bet_eta: datetime | None = None

    balance: float = 100.0  # virtuel en demo, reel en prod
    total_staked: float = 0.0
    total_won: float = 0.0
    total_lost: float = 0.0
    bets_total: int = 0
    bets_won: int = 0
    bets_lost: int = 0
    bets_skipped: int = 0

    last_event: str = ""
    started_at: datetime | None = None

    # signal d'arret SL/TP atteint
    halted_reason: str = ""

    @property
    def win_rate(self) -> float:
        decided = self.bets_won + self.bets_lost
        if decided == 0:
            return 0.0
        return round(100.0 * self.bets_won / decided, 2)

    @property
    def pnl(self) -> float:
        return round(self.total_won - self.total_lost, 4)


@dataclass
class _StateContainer:
    state: BotState = field(default_factory=BotState)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    listeners: list[asyncio.Queue[dict]] = field(default_factory=list)


_container = _StateContainer()


def get_state() -> BotState:
    return _container.state


async def update_state(**kwargs: object) -> BotState:
    async with _container.lock:
        s = _container.state
        for k, v in kwargs.items():
            if hasattr(s, k):
                setattr(s, k, v)
        await _broadcast({"type": "state", "data": serialize_state(s)})
        return s


def serialize_state(s: BotState) -> dict[str, object]:
    return {
        "running": s.running,
        "mode": s.mode,
        "bet_amount": s.bet_amount,
        "stop_loss": s.stop_loss,
        "take_profit": s.take_profit,
        "target_market": s.target_market,
        "btc_price": s.btc_price,
        "btc_trend": s.btc_trend,
        "last_candle_color": s.last_candle_color,
        "current_signal": s.current_signal,
        "next_bet_eta": s.next_bet_eta.isoformat() if s.next_bet_eta else None,
        "balance": round(s.balance, 4),
        "total_staked": round(s.total_staked, 4),
        "total_won": round(s.total_won, 4),
        "total_lost": round(s.total_lost, 4),
        "bets_total": s.bets_total,
        "bets_won": s.bets_won,
        "bets_lost": s.bets_lost,
        "bets_skipped": s.bets_skipped,
        "last_event": s.last_event,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "halted_reason": s.halted_reason,
        "win_rate": s.win_rate,
        "pnl": s.pnl,
        "server_time": datetime.now(tz=timezone.utc).isoformat(),
    }


async def _broadcast(event: dict[str, object]) -> None:
    for q in list(_container.listeners):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


async def publish(event_type: str, data: dict[str, object]) -> None:
    await _broadcast({"type": event_type, "data": data})


def subscribe() -> asyncio.Queue[dict]:
    q: asyncio.Queue[dict] = asyncio.Queue(maxsize=256)
    _container.listeners.append(q)
    return q


def unsubscribe(q: asyncio.Queue[dict]) -> None:
    if q in _container.listeners:
        _container.listeners.remove(q)
