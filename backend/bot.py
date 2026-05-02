"""Orchestrateur principal d'Oracle Bot."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend import models
from backend.binance_ws import BinanceClient, TickerSnapshot
from backend.config import BotMode, settings
from backend.db import SessionLocal, init_db
from backend.polymarket import PolymarketReader
from backend.state import get_state, publish, serialize_state, update_state
from backend.strategy import (
    Candle,
    CandleColor,
    Direction,
    binance_short_term_trend,
    evaluate_signal,
)
from backend.trader import PlacedBet, Trader, build_trader

logger = logging.getLogger(__name__)


class OracleBot:
    """Orchestrateur asyncio. Une seule instance par process."""

    def __init__(self) -> None:
        self.state = get_state()
        # Hydrater l'etat depuis la config
        self.state.mode = settings.mode.value
        self.state.bet_amount = settings.bet_amount
        self.state.stop_loss = settings.stop_loss
        self.state.take_profit = settings.take_profit
        self.state.balance = settings.demo_starting_balance

        self.binance = BinanceClient()
        self.polymarket = PolymarketReader()
        self.trader: Trader = build_trader(
            mode=self.state.mode,
            private_key=settings.polymarket_private_key,
            funder=settings.polymarket_funder_address,
            host=settings.polymarket_api_url,
        )

        # Notifier (Telegram ou no-op)
        from backend.telegram_bot import build_notifier

        self.notifier = build_notifier()

        self._tasks: list[asyncio.Task] = []
        self._lock = asyncio.Lock()
        self._pending_bets: list[tuple[PlacedBet, int, datetime]] = []
        self._last_candle_ts: float = 0.0

    # ---------- API publique ----------

    async def setup(self) -> None:
        """Initialise la base et amorce le prix BTC."""
        await init_db()
        try:
            price = await self.binance.fetch_spot_price()
            await update_state(btc_price=price)
            self.binance.recent_prices.append(price)
        except Exception as exc:
            logger.warning("Impossible de recuperer le prix spot Binance: %s", exc)

    async def start(self) -> None:
        async with self._lock:
            if self.state.running:
                return
            self.state.running = True
            self.state.started_at = datetime.now(tz=timezone.utc)
            self.state.halted_reason = ""
            await publish("state", serialize_state(self.state))

            self._tasks = [
                asyncio.create_task(self._stream_binance(), name="binance-ws"),
                asyncio.create_task(self._poll_polymarket(), name="poly-poll"),
                asyncio.create_task(self._resolve_loop(), name="resolve-loop"),
            ]
        await self.notifier.send("Oracle Bot demarre.")

    async def stop(self, reason: str = "") -> None:
        async with self._lock:
            if not self.state.running and not self._tasks:
                return
            self.state.running = False
            if reason:
                self.state.halted_reason = reason
            for t in self._tasks:
                t.cancel()
            self._tasks = []
            await publish("state", serialize_state(self.state))
        await self.notifier.send(f"Oracle Bot arrete{(' — ' + reason) if reason else ''}.")

    async def set_bet_amount(self, amount: float) -> None:
        await update_state(bet_amount=max(0.01, float(amount)))

    async def set_stop_loss(self, value: float) -> None:
        await update_state(stop_loss=max(0.0, float(value)))

    async def set_take_profit(self, value: float) -> None:
        await update_state(take_profit=max(0.0, float(value)))

    async def set_target_market(self, market: str) -> None:
        await update_state(target_market=market or "BTC-5min")

    async def set_mode(self, mode: BotMode) -> None:
        running = self.state.running
        if running:
            await self.stop("changement de mode")
        self.trader = build_trader(
            mode=mode.value,
            private_key=settings.polymarket_private_key,
            funder=settings.polymarket_funder_address,
            host=settings.polymarket_api_url,
        )
        await update_state(mode=mode.value)
        if running:
            await self.start()

    # ---------- Boucles internes ----------

    async def _stream_binance(self) -> None:
        try:
            await self.binance.stream_klines(self._on_tick, self._on_candle_close)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.exception("Stream Binance termine: %s", exc)
            await update_state(last_event=f"Erreur Binance: {exc}")

    async def _on_tick(self, snapshot: TickerSnapshot) -> None:
        prices = list(self.binance.recent_prices)
        trend = binance_short_term_trend(prices)
        await update_state(
            btc_price=snapshot.price,
            btc_trend=trend.value,
            last_candle_color=snapshot.candle.color.value,
        )

    async def _on_candle_close(self, candle: Candle) -> None:
        # Eviter les doubles traitements rapides
        now = datetime.now(tz=timezone.utc)
        if (now.timestamp() - self._last_candle_ts) < settings.candle_interval_seconds / 2:
            return
        self._last_candle_ts = now.timestamp()

        recent_prices = list(self.binance.recent_prices)
        signal = evaluate_signal(candle, recent_prices)

        await update_state(
            current_signal=signal.direction.value if signal.confirmed else "INCERTAIN",
            last_candle_color=candle.color.value,
            next_bet_eta=now + timedelta(seconds=settings.bet_resolution_seconds)
            if signal.confirmed
            else None,
        )

        if not signal.confirmed:
            await self._record_skip(signal.reason, candle)
            await self.notifier.send(f"Signal incertain — pari ignore ({signal.reason}).")
            return

        if not self.state.running:
            return

        # Lecture Polymarket pour PnL virtuel et logging
        market = await self.polymarket.fetch_btc_market()
        poly_price = (
            market.yes_price
            if market and signal.direction == Direction.UP
            else market.no_price
            if market
            else 0.5
        )

        placed = await self.trader.place_bet(
            direction=signal.direction,
            amount=self.state.bet_amount,
            entry_price=candle.close,
            polymarket_price=poly_price,
            market=self.state.target_market,
        )

        bet_id = await self._persist_bet(
            placed, signal_candle=candle.color, signal_trend=signal.binance_trend
        )
        self._pending_bets.append((placed, bet_id, now + timedelta(seconds=settings.bet_resolution_seconds)))

        await update_state(
            bets_total=self.state.bets_total + 1,
            total_staked=self.state.total_staked + placed.amount,
            last_event=f"Pari {placed.direction.value} {placed.amount:.2f} sur {placed.market}",
        )
        await self.notifier.send(
            f"[{placed.mode.upper()}] Pari {placed.direction.value} — "
            f"{placed.amount:.2f} USDC | {placed.market} @ BTC={placed.entry_price:.2f}"
        )

    async def _resolve_loop(self) -> None:
        """Toutes les 10s : resout les paris arrives a echeance avec le prix Binance courant."""
        try:
            while True:
                await asyncio.sleep(10)
                if not self._pending_bets:
                    continue
                now = datetime.now(tz=timezone.utc)
                still_pending: list[tuple[PlacedBet, int, datetime]] = []
                for placed, bet_id, deadline in self._pending_bets:
                    if now < deadline:
                        still_pending.append((placed, bet_id, deadline))
                        continue
                    exit_price = self.state.btc_price or placed.entry_price
                    status, pnl = await self.trader.resolve(placed, exit_price)
                    await self._mark_resolved(bet_id, status, pnl, exit_price)
                    won = status == models.BetStatus.WON
                    new_balance = self.state.balance + pnl
                    await update_state(
                        bets_won=self.state.bets_won + (1 if won else 0),
                        bets_lost=self.state.bets_lost + (0 if won else 1),
                        total_won=self.state.total_won + (pnl if won else 0),
                        total_lost=self.state.total_lost + (-pnl if not won else 0),
                        balance=new_balance,
                        last_event=f"{status.value} {pnl:+.2f} USDC",
                    )
                    icon = "GAGNE" if won else "PERDU"
                    await self.notifier.send(
                        f"[{placed.mode.upper()}] {icon} {pnl:+.2f} USDC | Solde: {new_balance:.2f}"
                    )
                    await self._check_sl_tp()
                self._pending_bets = still_pending
        except asyncio.CancelledError:
            return

    async def _poll_polymarket(self) -> None:
        try:
            while True:
                await asyncio.sleep(60)
                market = await self.polymarket.fetch_btc_market()
                if market is not None:
                    await publish(
                        "polymarket",
                        {
                            "slug": market.slug,
                            "question": market.question,
                            "yes_price": market.yes_price,
                            "no_price": market.no_price,
                        },
                    )
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.warning("Polymarket poll error: %s", exc)

    async def _check_sl_tp(self) -> None:
        s = self.state
        if s.stop_loss and s.pnl <= -abs(s.stop_loss):
            await self.notifier.send(f"Stop-Loss atteint ({s.pnl:+.2f}) — Bot arrete.")
            await self.stop("stop-loss atteint")
            return
        if s.take_profit and s.pnl >= abs(s.take_profit):
            await self.notifier.send(f"Take-Profit atteint ({s.pnl:+.2f}) — Bot arrete.")
            await self.stop("take-profit atteint")

    # ---------- Persistance ----------

    async def _persist_bet(
        self, placed: PlacedBet, signal_candle: CandleColor, signal_trend: Direction
    ) -> int:
        async with SessionLocal() as session:
            bet = models.Bet(
                mode=placed.mode,
                market=placed.market,
                direction=placed.direction.value,
                amount=placed.amount,
                entry_price=placed.entry_price,
                polymarket_price=placed.polymarket_price,
                status=models.BetStatus.PENDING.value,
                signal_candle=signal_candle.value,
                signal_binance_trend=signal_trend.value,
            )
            session.add(bet)
            await session.commit()
            await session.refresh(bet)
            await publish("bet", {"id": bet.id, "status": bet.status, "direction": bet.direction})
            return bet.id

    async def _mark_resolved(
        self, bet_id: int, status: models.BetStatus, pnl: float, exit_price: float
    ) -> None:
        async with SessionLocal() as session:
            bet = (
                await session.execute(select(models.Bet).where(models.Bet.id == bet_id))
            ).scalar_one_or_none()
            if bet is None:
                return
            bet.status = status.value
            bet.pnl = pnl
            bet.exit_price = exit_price
            bet.resolved_at = datetime.now(tz=timezone.utc)
            await session.commit()
            await publish(
                "bet",
                {"id": bet.id, "status": bet.status, "pnl": bet.pnl, "direction": bet.direction},
            )

    async def _record_skip(self, reason: str, candle: Candle) -> None:
        async with SessionLocal() as session:
            bet = models.Bet(
                mode=self.state.mode,
                market=self.state.target_market,
                direction=Direction.FLAT.value,
                amount=0.0,
                entry_price=candle.close,
                polymarket_price=0.0,
                status=models.BetStatus.SKIPPED.value,
                signal_candle=candle.color.value,
                signal_binance_trend="",
                notes=reason[:255],
            )
            session.add(bet)
            await session.commit()
        await update_state(bets_skipped=self.state.bets_skipped + 1, last_event=f"SKIP: {reason}")


# Singleton lazy
_bot_instance: OracleBot | None = None


def get_bot() -> OracleBot:
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = OracleBot()
    return _bot_instance
