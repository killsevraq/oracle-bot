"""Abstraction des traders DEMO et PROD avec la meme interface."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.models import BetDirection, BetStatus
from backend.strategy import Direction

logger = logging.getLogger(__name__)


@dataclass
class PlacedBet:
    direction: BetDirection
    amount: float
    entry_price: float
    polymarket_price: float
    market: str
    mode: str


class Trader:
    """Interface commune."""

    mode: str = "demo"

    async def place_bet(
        self,
        direction: Direction,
        amount: float,
        entry_price: float,
        polymarket_price: float,
        market: str,
    ) -> PlacedBet:
        raise NotImplementedError

    async def resolve(self, bet: PlacedBet, exit_price: float) -> tuple[BetStatus, float]:
        raise NotImplementedError


class DemoTrader(Trader):
    """Pari simule : pas d'argent, on calcule le PnL virtuellement.

    Modele simple : un pari UP gagne si exit_price > entry_price (idem DOWN inverse).
    Le payout virtuel se base sur le prix Polymarket UP/DOWN (proba implicite).
    Si le pari gagne et que la probabilite implicite etait p, le gain net = amount*(1/p - 1).
    """

    mode = "demo"

    async def place_bet(
        self,
        direction: Direction,
        amount: float,
        entry_price: float,
        polymarket_price: float,
        market: str,
    ) -> PlacedBet:
        bet_dir = BetDirection.UP if direction == Direction.UP else BetDirection.DOWN
        logger.info(
            "[DEMO] Pari simule %s %.2f USDC @ BTC=%.2f (poly=%.3f)",
            bet_dir.value,
            amount,
            entry_price,
            polymarket_price,
        )
        return PlacedBet(
            direction=bet_dir,
            amount=amount,
            entry_price=entry_price,
            polymarket_price=polymarket_price,
            market=market,
            mode=self.mode,
        )

    async def resolve(self, bet: PlacedBet, exit_price: float) -> tuple[BetStatus, float]:
        won = (bet.direction == BetDirection.UP and exit_price > bet.entry_price) or (
            bet.direction == BetDirection.DOWN and exit_price < bet.entry_price
        )
        if won:
            p = bet.polymarket_price if 0.0 < bet.polymarket_price < 1.0 else 0.5
            payout = bet.amount * (1.0 / p - 1.0)
            return BetStatus.WON, round(payout, 4)
        return BetStatus.LOST, -bet.amount


class ProdTrader(Trader):
    """Pari reel via py-clob-client. Charge la dependance a la demande."""

    mode = "prod"

    def __init__(self, private_key: str, funder_address: str, host: str) -> None:
        self.private_key = private_key
        self.funder_address = funder_address
        self.host = host
        self._client = None

    def _get_client(self):  # type: ignore[no-untyped-def]
        if self._client is None:
            try:
                from py_clob_client.client import ClobClient  # type: ignore[import-not-found]
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "py-clob-client non installe. Faire `pip install '.[prod]'` pour activer le mode prod."
                ) from exc
            self._client = ClobClient(
                host=self.host,
                key=self.private_key,
                chain_id=137,
                funder=self.funder_address,
            )
        return self._client

    async def place_bet(
        self,
        direction: Direction,
        amount: float,
        entry_price: float,
        polymarket_price: float,
        market: str,
    ) -> PlacedBet:
        # Implementation reelle a brancher : selectionner le token YES/NO du marche
        # cible et poster un ordre via self._get_client().create_and_post_order(...)
        bet_dir = BetDirection.UP if direction == Direction.UP else BetDirection.DOWN
        logger.warning(
            "[PROD] Placeholder ordre %s %.2f USDC @ BTC=%.2f sur %s — a brancher py-clob-client.",
            bet_dir.value,
            amount,
            entry_price,
            market,
        )
        return PlacedBet(
            direction=bet_dir,
            amount=amount,
            entry_price=entry_price,
            polymarket_price=polymarket_price,
            market=market,
            mode=self.mode,
        )

    async def resolve(self, bet: PlacedBet, exit_price: float) -> tuple[BetStatus, float]:
        # En prod, la resolution vient de Polymarket (settlement on-chain).
        # Ici on reapplique la meme logique que DemoTrader pour le PnL, en attendant
        # le branchement complet du suivi de position via l'API CLOB.
        won = (bet.direction == BetDirection.UP and exit_price > bet.entry_price) or (
            bet.direction == BetDirection.DOWN and exit_price < bet.entry_price
        )
        if won:
            p = bet.polymarket_price if 0.0 < bet.polymarket_price < 1.0 else 0.5
            return BetStatus.WON, round(bet.amount * (1.0 / p - 1.0), 4)
        return BetStatus.LOST, -bet.amount


def build_trader(mode: str, private_key: str, funder: str, host: str) -> Trader:
    if mode == "prod":
        if not private_key or not funder:
            logger.warning(
                "MODE=prod mais POLYMARKET_PRIVATE_KEY/FUNDER manquants — fallback sur DemoTrader."
            )
            return DemoTrader()
        return ProdTrader(private_key=private_key, funder_address=funder, host=host)
    return DemoTrader()
