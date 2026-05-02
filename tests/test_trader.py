"""Tests unitaires du trader DEMO."""

from __future__ import annotations

import pytest

from backend.models import BetDirection, BetStatus
from backend.strategy import Direction
from backend.trader import DemoTrader, build_trader


@pytest.mark.asyncio
async def test_demo_trader_win_up():
    trader = DemoTrader()
    placed = await trader.place_bet(
        direction=Direction.UP,
        amount=10.0,
        entry_price=100.0,
        polymarket_price=0.5,
        market="BTC-5min",
    )
    assert placed.direction == BetDirection.UP
    status, pnl = await trader.resolve(placed, exit_price=110.0)
    assert status == BetStatus.WON
    # payout net = amount * (1/p - 1) = 10 * (2 - 1) = 10
    assert pnl == 10.0


@pytest.mark.asyncio
async def test_demo_trader_loss_up():
    trader = DemoTrader()
    placed = await trader.place_bet(
        direction=Direction.UP,
        amount=5.0,
        entry_price=100.0,
        polymarket_price=0.5,
        market="BTC-5min",
    )
    status, pnl = await trader.resolve(placed, exit_price=99.0)
    assert status == BetStatus.LOST
    assert pnl == -5.0


@pytest.mark.asyncio
async def test_demo_trader_win_down():
    trader = DemoTrader()
    placed = await trader.place_bet(
        direction=Direction.DOWN,
        amount=4.0,
        entry_price=100.0,
        polymarket_price=0.4,
        market="BTC-5min",
    )
    status, pnl = await trader.resolve(placed, exit_price=99.0)
    assert status == BetStatus.WON
    # payout = 4 * (1/0.4 - 1) = 4 * 1.5 = 6
    assert pnl == 6.0


def test_build_trader_falls_back_to_demo_when_prod_misconfigured():
    trader = build_trader(mode="prod", private_key="", funder="", host="https://x")
    assert trader.mode == "demo"
    trader_demo = build_trader(mode="demo", private_key="", funder="", host="https://x")
    assert trader_demo.mode == "demo"
