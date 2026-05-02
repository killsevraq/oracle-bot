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


@pytest.mark.asyncio
async def test_demo_trader_realistic_payout_low_price():
    """Pari achete a 0.30 -> payout = mise * (1 - 0.30) / 0.30 = mise * 7/3."""
    trader = DemoTrader()
    placed = await trader.place_bet(
        direction=Direction.UP,
        amount=5.0,
        entry_price=78000.0,
        polymarket_price=0.30,
        market="BTC-5min",
    )
    status, pnl = await trader.resolve(placed, exit_price=78050.0)
    assert status == BetStatus.WON
    # 5 * (1/0.30 - 1) = 5 * 7/3 ≈ 11.6667
    assert abs(pnl - 11.6667) < 0.001


@pytest.mark.asyncio
async def test_demo_trader_realistic_payout_high_price():
    """Pari a 0.80 (favori) -> payout = 5 * (1/0.80 - 1) = 1.25 USDC, perte=-5."""
    trader = DemoTrader()
    placed = await trader.place_bet(
        direction=Direction.UP,
        amount=5.0,
        entry_price=78000.0,
        polymarket_price=0.80,
        market="BTC-5min",
    )
    status, pnl = await trader.resolve(placed, exit_price=78050.0)
    assert status == BetStatus.WON
    assert abs(pnl - 1.25) < 0.001
    # Et a la perte on garde -mise pleine
    placed2 = await trader.place_bet(
        direction=Direction.UP,
        amount=5.0,
        entry_price=78000.0,
        polymarket_price=0.80,
        market="BTC-5min",
    )
    status2, pnl2 = await trader.resolve(placed2, exit_price=77900.0)
    assert status2 == BetStatus.LOST
    assert pnl2 == -5.0


@pytest.mark.asyncio
async def test_demo_trader_clamps_invalid_price():
    """Si le prix est aberrant (<=0 ou >=1), le DemoTrader retombe sur 0.5."""
    trader = DemoTrader()
    placed = await trader.place_bet(
        direction=Direction.UP,
        amount=5.0,
        entry_price=78000.0,
        polymarket_price=0.0,
        market="BTC-5min",
    )
    status, pnl = await trader.resolve(placed, exit_price=78050.0)
    assert status == BetStatus.WON
    # fallback p=0.5 -> payout = 5 * 1 = 5
    assert pnl == 5.0


def test_build_trader_falls_back_to_demo_when_prod_misconfigured():
    trader = build_trader(mode="prod", private_key="", funder="", host="https://x")
    assert trader.mode == "demo"
    trader_demo = build_trader(mode="demo", private_key="", funder="", host="https://x")
    assert trader_demo.mode == "demo"
