"""Client WebSocket Binance pour les bougies BTC 10min."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import httpx
import websockets

from backend.config import settings
from backend.strategy import Candle

logger = logging.getLogger(__name__)


@dataclass
class TickerSnapshot:
    price: float
    candle: Candle


class BinanceClient:
    """Stream les bougies BTC 10min via WebSocket et garde un buffer de prix recents."""

    def __init__(
        self,
        ws_url: str | None = None,
        rest_url: str | None = None,
        symbol: str | None = None,
        recent_window: int = 30,
    ) -> None:
        self.ws_url = ws_url or settings.binance_ws_url
        self.rest_url = rest_url or settings.binance_rest_url
        self.symbol = (symbol or settings.binance_symbol).upper()
        self.recent_prices: deque[float] = deque(maxlen=recent_window)
        self._stop = asyncio.Event()

    async def fetch_spot_price(self) -> float:
        """Recupere un prix spot via l'API REST publique (fallback / bootstrap)."""
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{self.rest_url}/api/v3/ticker/price", params={"symbol": self.symbol})
            r.raise_for_status()
            data = r.json()
            return float(data["price"])

    async def stream_klines(
        self,
        on_tick: Callable[[TickerSnapshot], Awaitable[None]],
        on_candle_close: Callable[[Candle], Awaitable[None]],
    ) -> None:
        """Boucle infinie : ecoute Binance et appelle les callbacks fournis."""
        backoff = 1.0
        while not self._stop.is_set():
            try:
                async for snapshot in self._iter_messages():
                    self.recent_prices.append(snapshot.price)
                    await on_tick(snapshot)
                    if snapshot.candle.is_closed:
                        await on_candle_close(snapshot.candle)
                    backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Binance WS deconnecte: %s — retry dans %.1fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    async def _iter_messages(self) -> AsyncIterator[TickerSnapshot]:
        async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=20) as ws:
            logger.info("Connecte a Binance WS: %s", self.ws_url)
            n = 0
            async for raw in ws:
                if self._stop.is_set():
                    break
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    logger.debug("WS message JSON invalide: %r", raw[:200])
                    continue
                k = msg.get("k") or {}
                if not k:
                    logger.warning("WS message sans 'k': %r", msg)
                    continue
                try:
                    candle = Candle(
                        open_price=float(k["o"]),
                        high=float(k["h"]),
                        low=float(k["l"]),
                        close=float(k["c"]),
                        is_closed=bool(k.get("x", False)),
                    )
                except (KeyError, ValueError) as exc:
                    logger.warning("WS candle parse error: %s — payload=%r", exc, k)
                    continue
                n += 1
                if n <= 3 or n % 100 == 0 or candle.is_closed:
                    logger.info(
                        "WS tick #%d: close=%.2f open=%.2f closed=%s",
                        n,
                        candle.close,
                        candle.open_price,
                        candle.is_closed,
                    )
                yield TickerSnapshot(price=candle.close, candle=candle)

    def stop(self) -> None:
        self._stop.set()
