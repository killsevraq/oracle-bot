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
from backend.polymarket_clob import (
    Btc5MinMarket,
    PolymarketClobClient,
    fair_yes_probability,
)
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
        self.clob = PolymarketClobClient()
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
        # Etat strategie arbitrage
        self._arb_market: Btc5MinMarket | None = None
        self._arb_strike: float = 0.0  # BTC capture au debut de la fenetre courante
        self._arb_bet_placed_for_slug: str = ""  # un seul pari par fenetre Polymarket

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
            if settings.signal_mode == "arbitrage":
                self._tasks.append(asyncio.create_task(self._arbitrage_loop(), name="arbitrage-loop"))
                logger.info(
                    "Mode arbitrage actif (poll %.1fs, seuil %.2f, vol %.2f%% / 5min)",
                    settings.arbitrage_poll_interval,
                    settings.arbitrage_threshold,
                    settings.vol_5min_pct,
                )
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
        trend = binance_short_term_trend(prices, threshold_pct=settings.binance_trend_threshold_pct)
        await update_state(
            btc_price=snapshot.price,
            btc_trend=trend.value,
            last_candle_color=snapshot.candle.color.value,
            last_tick_at=datetime.now(tz=timezone.utc),
            tick_count=self.state.tick_count + 1,
        )

    async def _on_candle_close(self, candle: Candle) -> None:
        # Eviter les doubles traitements rapides
        now = datetime.now(tz=timezone.utc)
        if (now.timestamp() - self._last_candle_ts) < settings.candle_interval_seconds / 2:
            logger.info("Candle close ignoree (trop proche de la precedente)")
            return
        self._last_candle_ts = now.timestamp()

        recent_prices = list(self.binance.recent_prices)
        signal = evaluate_signal(
            candle,
            recent_prices,
            min_body_pct=settings.min_candle_body_pct,
            trend_threshold_pct=settings.binance_trend_threshold_pct,
        )
        logger.info(
            "Candle CLOSE #%d: color=%s open=%.2f close=%.2f signal=%s confirmed=%s reason=%s",
            self.state.candle_close_count + 1,
            candle.color.value,
            candle.open_price,
            candle.close,
            signal.direction.value,
            signal.confirmed,
            signal.reason,
        )
        await update_state(
            last_candle_close_at=now,
            candle_close_count=self.state.candle_close_count + 1,
        )

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

        # Mode arbitrage : la decision de pari est prise dans _arbitrage_loop, pas ici.
        if settings.signal_mode == "arbitrage":
            logger.info("Signal candle ignore (mode=arbitrage)")
            return

        # Filtre 3 : confirmation post-cloture. On attend N sec et on verifie que le prix
        # continue dans la direction du signal. Si retournement immediat, on skip.
        if settings.post_close_confirmation_seconds > 0:
            await asyncio.sleep(settings.post_close_confirmation_seconds)
            current_price = self.state.btc_price or candle.close
            continued = (signal.direction == Direction.UP and current_price >= candle.close) or (
                signal.direction == Direction.DOWN and current_price <= candle.close
            )
            if not continued:
                reason = (
                    f"retournement post-cloture ({signal.direction.value}, "
                    f"close={candle.close:.2f} -> spot={current_price:.2f})"
                )
                logger.info("Skip post-cloture: %s", reason)
                await self._record_skip(reason, candle)
                await self.notifier.send(f"Signal annule par retournement post-cloture ({reason}).")
                await update_state(current_signal="INCERTAIN", next_bet_eta=None)
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

    async def _arbitrage_loop(self) -> None:
        """Detecte le retard du carnet Polymarket vs Binance et place des paris.

        - On suit le marche BTC 5min Polymarket courant (via la serie).
        - On capture le strike (BTC au debut de la fenetre = open Binance).
        - On poll le carnet d'ordres YES toutes les `arbitrage_poll_interval` secondes.
        - On compare fair_yes (calculee depuis Binance) avec market_yes (carnet CLOB).
        - Si l'ecart depasse `arbitrage_threshold`, on parie (un seul pari par fenetre).
        """
        try:
            while True:
                await asyncio.sleep(settings.arbitrage_poll_interval)
                if not self.state.running:
                    continue
                try:
                    await self._handle_arbitrage_tick()
                except Exception as exc:
                    logger.warning("Arbitrage tick error: %s", exc)
        except asyncio.CancelledError:
            return

    async def _refresh_arbitrage_market(self) -> bool:
        """Met a jour le marche Polymarket courant. Retourne True si on en a un."""
        market = await self.clob.find_current_market()
        if market is None:
            self._arb_market = None
            return False
        if not self._arb_market or self._arb_market.slug != market.slug:
            # Nouvelle fenetre : on capture le strike depuis le BTC actuel et on reset.
            self._arb_market = market
            self._arb_strike = self.state.btc_price or 0.0
            self._arb_bet_placed_for_slug = ""
            logger.info(
                "Arbitrage: nouvelle fenetre %s end=%s strike=%.2f",
                market.slug,
                datetime.fromtimestamp(market.end_ts, tz=timezone.utc).isoformat(),
                self._arb_strike,
            )
        return True

    async def _handle_arbitrage_tick(self) -> None:
        if not await self._refresh_arbitrage_market():
            return
        market = self._arb_market
        if market is None:
            return
        if self._arb_bet_placed_for_slug == market.slug:
            return
        if self._arb_strike <= 0:
            self._arb_strike = self.state.btc_price or 0.0
            return
        btc_now = self.state.btc_price or 0.0
        if btc_now <= 0:
            return
        now_ts = datetime.now(tz=timezone.utc).timestamp()
        time_remaining = max(0.0, market.end_ts - now_ts)
        if time_remaining < 30.0:
            # Trop tard pour parier (on n'aurait pas le temps de profiter du retard).
            return

        fair_yes = fair_yes_probability(
            btc_now=btc_now,
            btc_strike=self._arb_strike,
            time_remaining_s=time_remaining,
            vol_5min_pct=settings.vol_5min_pct,
        )

        # Carnet YES Polymarket
        yes_book = await self.clob.fetch_book(market.yes_token_id)
        if yes_book is None:
            return

        # Decision : si fair_yes > best_ask + seuil => buy YES (UP, sous-evalue).
        #            si fair_yes < best_bid - seuil => buy NO (DOWN, sur-evalue).
        edge_up = fair_yes - yes_book.best_ask
        edge_down = yes_book.best_bid - fair_yes
        logger.info(
            "Arbitrage tick: btc=%.2f strike=%.2f fair_yes=%.3f mkt_bid=%.3f mkt_ask=%.3f "
            "edge_up=%+.3f edge_down=%+.3f trem=%.0fs",
            btc_now,
            self._arb_strike,
            fair_yes,
            yes_book.best_bid,
            yes_book.best_ask,
            edge_up,
            edge_down,
            time_remaining,
        )

        threshold = settings.arbitrage_threshold
        if edge_up >= threshold and 0.0 < yes_book.best_ask < 1.0:
            await self._place_arbitrage_bet(
                direction=Direction.UP,
                fair_yes=fair_yes,
                market_price=yes_book.best_ask,
                market=market,
                btc_now=btc_now,
            )
        elif edge_down >= threshold and 0.0 < yes_book.best_bid < 1.0:
            # On veut acheter NO -> on entre a 1 - best_bid (best ask sur NO ~ 1 - best_bid YES).
            no_price = 1.0 - yes_book.best_bid
            await self._place_arbitrage_bet(
                direction=Direction.DOWN,
                fair_yes=fair_yes,
                market_price=no_price,
                market=market,
                btc_now=btc_now,
            )

    async def _place_arbitrage_bet(
        self,
        *,
        direction: Direction,
        fair_yes: float,
        market_price: float,
        market: Btc5MinMarket,
        btc_now: float,
    ) -> None:
        # Pour le pari arbitrage : entry_price = STRIKE (= BTC au debut de la fenetre).
        # On gagne si BTC final > strike (UP) ou BTC final < strike (DOWN).
        placed = await self.trader.place_bet(
            direction=direction,
            amount=self.state.bet_amount,
            entry_price=self._arb_strike,
            polymarket_price=market_price,
            market=f"BTC-5min-arbitrage:{market.slug}",
        )
        bet_id = await self._persist_bet(
            placed,
            signal_candle=CandleColor.NONE,
            signal_trend=Direction.FLAT,
        )
        deadline = datetime.fromtimestamp(market.end_ts, tz=timezone.utc)
        self._pending_bets.append((placed, bet_id, deadline))
        self._arb_bet_placed_for_slug = market.slug
        await update_state(
            bets_total=self.state.bets_total + 1,
            total_staked=self.state.total_staked + placed.amount,
            current_signal=direction.value,
            next_bet_eta=deadline,
            last_event=(
                f"Arbitrage {direction.value} {placed.amount:.2f} @ "
                f"poly={market_price:.3f} fair={fair_yes:.3f} "
                f"strike={self._arb_strike:.2f} btc={btc_now:.2f}"
            ),
        )
        await self.notifier.send(
            f"[ARBITRAGE {placed.mode.upper()}] {direction.value} "
            f"{placed.amount:.2f} USDC @ poly={market_price:.3f} "
            f"fair={fair_yes:.3f} (edge {abs(fair_yes - market_price):+.3f}) "
            f"strike={self._arb_strike:.2f}"
        )
        logger.info(
            "Arbitrage BET placed: dir=%s poly=%.3f fair=%.3f edge=%+.3f strike=%.2f end=%s",
            direction.value,
            market_price,
            fair_yes,
            fair_yes - market_price if direction == Direction.UP else market_price - (1 - fair_yes),
            self._arb_strike,
            deadline.isoformat(),
        )

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
