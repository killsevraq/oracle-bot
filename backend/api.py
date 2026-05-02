"""Routes REST + flux SSE temps reel."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from backend import models
from backend.bot import OracleBot, get_bot
from backend.config import BotMode
from backend.db import get_session
from backend.state import get_state, serialize_state, subscribe, unsubscribe

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["oracle-bot"])


def _bot() -> OracleBot:
    return get_bot()


# ---------- Schemas ----------


class BetAmountIn(BaseModel):
    amount: float = Field(gt=0)


class StopLossIn(BaseModel):
    value: float = Field(ge=0)


class TakeProfitIn(BaseModel):
    value: float = Field(ge=0)


class TargetMarketIn(BaseModel):
    market: str


class ModeIn(BaseModel):
    mode: BotMode


class BetOut(BaseModel):
    id: int
    created_at: str
    resolved_at: str | None
    mode: str
    market: str
    direction: str
    amount: float
    entry_price: float
    polymarket_price: float
    exit_price: float | None
    status: str
    pnl: float
    signal_candle: str
    signal_binance_trend: str
    notes: str
    strategy: str


# ---------- Endpoints ----------


@router.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok"}


@router.get("/state")
async def state() -> dict[str, Any]:
    return serialize_state(get_state())


@router.post("/bot/start")
async def start_bot(bot: OracleBot = Depends(_bot)) -> dict[str, Any]:
    await bot.start()
    return serialize_state(get_state())


@router.post("/bot/stop")
async def stop_bot(bot: OracleBot = Depends(_bot)) -> dict[str, Any]:
    await bot.stop("arret manuel")
    return serialize_state(get_state())


@router.post("/bot/bet-amount")
async def set_bet_amount(payload: BetAmountIn, bot: OracleBot = Depends(_bot)) -> dict[str, Any]:
    await bot.set_bet_amount(payload.amount)
    return serialize_state(get_state())


@router.post("/bot/stop-loss")
async def set_stop_loss(payload: StopLossIn, bot: OracleBot = Depends(_bot)) -> dict[str, Any]:
    await bot.set_stop_loss(payload.value)
    return serialize_state(get_state())


@router.post("/bot/take-profit")
async def set_take_profit(payload: TakeProfitIn, bot: OracleBot = Depends(_bot)) -> dict[str, Any]:
    await bot.set_take_profit(payload.value)
    return serialize_state(get_state())


@router.post("/bot/target-market")
async def set_target_market(payload: TargetMarketIn, bot: OracleBot = Depends(_bot)) -> dict[str, Any]:
    await bot.set_target_market(payload.market)
    return serialize_state(get_state())


@router.post("/bot/mode")
async def set_mode(payload: ModeIn, bot: OracleBot = Depends(_bot)) -> dict[str, Any]:
    await bot.set_mode(payload.mode)
    return serialize_state(get_state())


@router.get("/bets", response_model=list[BetOut])
async def list_bets(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    strategy: str | None = Query(default=None, description="Filtre par strategie (candle/arbitrage)."),
    session: AsyncSession = Depends(get_session),
) -> list[BetOut]:
    stmt = select(models.Bet).order_by(desc(models.Bet.created_at)).offset(offset).limit(limit)
    if strategy:
        stmt = stmt.where(models.Bet.strategy == strategy)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        BetOut(
            id=r.id,
            created_at=r.created_at.isoformat() if r.created_at else "",
            resolved_at=r.resolved_at.isoformat() if r.resolved_at else None,
            mode=r.mode,
            market=r.market,
            direction=r.direction,
            amount=r.amount,
            entry_price=r.entry_price,
            polymarket_price=r.polymarket_price,
            exit_price=r.exit_price,
            status=r.status,
            pnl=r.pnl,
            signal_candle=r.signal_candle,
            signal_binance_trend=r.signal_binance_trend,
            notes=r.notes,
            strategy=r.strategy or "candle",
        )
        for r in rows
    ]


def _strategy_breakdown(rows: list[models.Bet]) -> dict[str, dict[str, Any]]:
    """Aggrege W/L/skip/PnL par strategie."""
    breakdown: dict[str, dict[str, Any]] = {}
    for r in rows:
        key = r.strategy or "candle"
        b = breakdown.setdefault(
            key,
            {
                "strategy": key,
                "bets_total": 0,
                "bets_won": 0,
                "bets_lost": 0,
                "bets_skipped": 0,
                "total_staked": 0.0,
                "pnl": 0.0,
            },
        )
        if r.status == models.BetStatus.SKIPPED.value:
            b["bets_skipped"] += 1
            continue
        if r.amount > 0:
            b["bets_total"] += 1
            b["total_staked"] += r.amount
        if r.status == models.BetStatus.WON.value:
            b["bets_won"] += 1
            b["pnl"] += r.pnl
        elif r.status == models.BetStatus.LOST.value:
            b["bets_lost"] += 1
            b["pnl"] += r.pnl
    for b in breakdown.values():
        resolved = b["bets_won"] + b["bets_lost"]
        b["win_rate"] = (b["bets_won"] / resolved * 100.0) if resolved else 0.0
        b["pnl"] = round(b["pnl"], 4)
        b["total_staked"] = round(b["total_staked"], 4)
        b["win_rate"] = round(b["win_rate"], 2)
    return breakdown


@router.get("/stats")
async def stats(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    rows = (await session.execute(select(models.Bet).order_by(models.Bet.created_at))).scalars().all()
    cumulative_by_strategy: dict[str, list[dict[str, float | str]]] = {}
    pnl_acc: dict[str, float] = {}
    cumulative = []
    pnl = 0.0
    for r in rows:
        if r.status not in (models.BetStatus.WON.value, models.BetStatus.LOST.value):
            continue
        ts = r.resolved_at.isoformat() if r.resolved_at else r.created_at.isoformat()
        pnl += r.pnl
        cumulative.append({"ts": ts, "pnl": round(pnl, 4)})
        key = r.strategy or "candle"
        pnl_acc[key] = pnl_acc.get(key, 0.0) + r.pnl
        cumulative_by_strategy.setdefault(key, []).append({"ts": ts, "pnl": round(pnl_acc[key], 4)})
    s = get_state()
    breakdown = _strategy_breakdown(list(rows))
    return {
        "win_rate": s.win_rate,
        "pnl": s.pnl,
        "balance": s.balance,
        "total_staked": s.total_staked,
        "bets_total": s.bets_total,
        "bets_won": s.bets_won,
        "bets_lost": s.bets_lost,
        "bets_skipped": s.bets_skipped,
        "cumulative_pnl": cumulative,
        "by_strategy": breakdown,
        "cumulative_pnl_by_strategy": cumulative_by_strategy,
    }


@router.get("/events")
async def events() -> EventSourceResponse:
    """Server-Sent Events : push de l'etat + paris en temps reel."""

    queue = subscribe()

    async def gen():
        try:
            yield {"event": "state", "data": json.dumps(serialize_state(get_state()))}
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                yield {"event": msg.get("type", "message"), "data": json.dumps(msg.get("data", {}))}
        finally:
            unsubscribe(queue)

    return EventSourceResponse(gen())


# Route HTTP utilitaire pour le debug
@router.get("/debug/polymarket")
async def debug_polymarket(slug: str | None = None) -> dict[str, Any]:
    bot = get_bot()
    if slug:
        market = await bot.polymarket.fetch_market(slug)
    else:
        market = await bot.polymarket.fetch_btc_market()
    if market is None:
        raise HTTPException(status_code=404, detail="Aucun marche trouve")
    return {
        "slug": market.slug,
        "question": market.question,
        "yes_price": market.yes_price,
        "no_price": market.no_price,
        "end_date": market.end_date,
    }
