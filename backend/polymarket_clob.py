"""Client CLOB Polymarket pour la strategie d'arbitrage du lag Binance vs Polymarket.

Idee : Polymarket reagit avec un retard par rapport a Binance. On compare le prix
"juste" (fair value) calcule a partir du BTC Binance avec le prix YES affiche sur
Polymarket (carnet d'ordres CLOB). Si l'ecart depasse un seuil, on parie.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)


@dataclass
class Btc5MinMarket:
    """Snapshot d'un marche BTC up/down 5min Polymarket."""

    slug: str
    end_ts: float  # Unix epoch seconds (resolution time)
    yes_token_id: str
    no_token_id: str
    market_id: str = ""


@dataclass
class BookSnapshot:
    """Meilleurs bid/ask + mid d'un token CLOB."""

    best_bid: float  # 0..1, prix max qu'un acheteur paie
    best_ask: float  # 0..1, prix min qu'un vendeur accepte
    mid: float  # (bid + ask) / 2

    @property
    def spread(self) -> float:
        return max(0.0, self.best_ask - self.best_bid)


def fair_yes_probability(
    btc_now: float,
    btc_strike: float,
    time_remaining_s: float,
    vol_5min_pct: float = 0.20,
) -> float:
    """Probabilite "juste" que BTC finisse >= strike a la fin de la fenetre 5min.

    Modele : BTC ~ marche aleatoire normal avec volatilite vol_5min_pct sur 5 min.
    Sigma sur la duree restante = vol_5min_pct% * sqrt(time_remaining / 300).

    Args:
        btc_now: Prix BTC courant Binance.
        btc_strike: Prix BTC au debut de la fenetre 5min (= strike).
        time_remaining_s: Secondes avant la resolution.
        vol_5min_pct: Volatilite estimee sur 5 min en %. 0.20 = 0.2%.

    Retourne une probabilite entre 0 et 1.
    """
    if btc_strike <= 0:
        return 0.5
    if time_remaining_s <= 0:
        return 1.0 if btc_now > btc_strike else (0.0 if btc_now < btc_strike else 0.5)
    sigma = (vol_5min_pct / 100.0) * math.sqrt(time_remaining_s / 300.0)
    if sigma <= 0:
        return 0.5
    move = (btc_now - btc_strike) / btc_strike
    z = move / sigma
    # CDF normale standard via erf
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _best_prices_from_book(payload: dict) -> BookSnapshot:
    """Extrait best_bid / best_ask d'un payload `/book` Polymarket."""
    bids_raw = payload.get("bids") or []
    asks_raw = payload.get("asks") or []
    bids = sorted(
        (float(b["price"]) for b in bids_raw if b.get("price") is not None),
        reverse=True,
    )
    asks = sorted(float(a["price"]) for a in asks_raw if a.get("price") is not None)
    best_bid = bids[0] if bids else 0.0
    best_ask = asks[0] if asks else 1.0
    mid = (best_bid + best_ask) / 2.0 if (bids and asks) else (best_bid or best_ask or 0.5)
    return BookSnapshot(best_bid=best_bid, best_ask=best_ask, mid=mid)


class PolymarketClobClient:
    """Client minimal pour la lecture publique du CLOB Polymarket."""

    def __init__(
        self,
        clob_url: str | None = None,
        gamma_url: str | None = None,
        series_slug: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.clob_url = (clob_url or settings.polymarket_api_url).rstrip("/")
        self.gamma_url = (gamma_url or settings.polymarket_gamma_url).rstrip("/")
        self.series_slug = series_slug or settings.polymarket_btc_series_slug
        self.timeout = timeout
        self._series_id: str | None = None

    async def _resolve_series_id(self, client: httpx.AsyncClient) -> str | None:
        if self._series_id:
            return self._series_id
        r = await client.get(
            f"{self.gamma_url}/series",
            params={"slug": self.series_slug, "limit": 1},
        )
        if r.status_code != 200:
            logger.warning("Polymarket /series %s -> %s", self.series_slug, r.status_code)
            return None
        data = r.json() or []
        if not data:
            return None
        self._series_id = str(data[0].get("id") or "")
        return self._series_id or None

    async def find_current_market(self, now: datetime | None = None) -> Btc5MinMarket | None:
        """Trouve le marche BTC 5min dont la fenetre de resolution englobe `now`."""
        ts_now = (now or datetime.now(tz=timezone.utc)).timestamp()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            series_id = await self._resolve_series_id(client)
            if not series_id:
                return None
            r = await client.get(
                f"{self.gamma_url}/events",
                params={
                    "series_id": series_id,
                    "closed": "false",
                    "limit": 50,
                    "order": "startDate",
                    "ascending": "false",
                },
            )
            if r.status_code != 200:
                logger.warning("Polymarket /events -> %s", r.status_code)
                return None
            events = r.json() or []
            best: Btc5MinMarket | None = None
            best_diff = float("inf")
            for e in events:
                end_str = (e.get("endDate") or "").replace("Z", "+00:00")
                try:
                    end_ts = datetime.fromisoformat(end_str).timestamp()
                except ValueError:
                    continue
                # On veut un evenement encore ouvert (end > now) et proche de maintenant.
                if end_ts <= ts_now:
                    continue
                diff = end_ts - ts_now
                if diff > best_diff:
                    continue
                markets = e.get("markets") or []
                if not markets:
                    continue
                m = markets[0]
                if not m.get("enableOrderBook"):
                    continue
                tokens = m.get("clobTokenIds")
                if isinstance(tokens, str):
                    import json

                    try:
                        tokens = json.loads(tokens)
                    except ValueError:
                        tokens = []
                if not isinstance(tokens, list) or len(tokens) < 2:
                    continue
                best_diff = diff
                best = Btc5MinMarket(
                    slug=str(m.get("slug") or e.get("slug") or ""),
                    end_ts=end_ts,
                    yes_token_id=str(tokens[0]),
                    no_token_id=str(tokens[1]),
                    market_id=str(m.get("conditionId") or m.get("id") or ""),
                )
            return best

    async def fetch_book(self, token_id: str) -> BookSnapshot | None:
        """Recupere le carnet d'ordres pour un token et retourne best bid/ask."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(f"{self.clob_url}/book", params={"token_id": token_id})
            if r.status_code != 200:
                return None
            try:
                payload = r.json()
            except ValueError:
                return None
            return _best_prices_from_book(payload)
